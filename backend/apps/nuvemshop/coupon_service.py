"""Orquestração fail-closed da criação OAuth do cupom do voucher.

Não habilita cashback. Uma criação de cupom com resposta incerta vira
pendência de reconciliação; não se repete POST automaticamente.
"""
import hashlib
import secrets
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.loyalty.models import LoyaltyVoucher
from apps.participants.models import ProgramParticipant
from apps.customers.models import CustomerProfile, VerifiedCustomerContact
from apps.customers.services import find_verified_customer
from apps.loyalty.services import _code_digests
from apps.tenants.models import Tenant
from .coupon_client import (
    CouponRemoteError, coupon_payload, create_coupon_once, find_coupon_exact,
)
from .models import NuvemshopCouponIntent, NuvemshopInstallation, NuvemshopCouponOwnershipIncident
from .scopes import parse_scopes
from .security import config, decrypt_token, encrypt_token


class PilotCouponBlocked(ValueError):
    pass


def _assert_verified_preissue_owner(voucher):
    """Server-side ownership proof BEFORE emitting the code to the provider.

    Existing OTP/provider-verified identifiers bind the voucher to one member.
    This does not prove that the same person will use the code at checkout.
    """
    if voucher.participant.status != ProgramParticipant.Status.ACTIVE:
        raise PilotCouponBlocked("Participante sem adesão vigente.")
    profile = CustomerProfile.objects.filter(
        tenant_id=voucher.tenant_id, participant_id=voucher.participant_id,
    ).first()
    if profile is None or not profile.verified_contacts.filter(
        kind__in=(VerifiedCustomerContact.Kind.EMAIL,
                  VerifiedCustomerContact.Kind.PHONE),
    ).exists():
        raise PilotCouponBlocked("Emissão exige contato comprovado do titular.")
    email = voucher.participant.contact_email
    if email:
        try:
            resolved = find_verified_customer(
                tenant_id=voucher.tenant_id, email=email,
            )
        except ValueError:
            raise PilotCouponBlocked("E-mail do participante inválido.") from None
        if resolved is None or resolved.pk != profile.pk:
            raise PilotCouponBlocked("E-mail do participante não corresponde ao titular.")
    if profile.verified_contacts.filter(
        kind=VerifiedCustomerContact.Kind.CPF,
    ).exclude(proof_method="provider_confirmed").exists():
        raise PilotCouponBlocked("CPF não possui prova do provedor.")


def _context(voucher):
    """Credenciais apenas server-side e específicas da instalação e loja."""
    tenant = voucher.tenant
    if (tenant.status != Tenant.Status.ACTIVE or tenant.platform != "nuvemshop"
            or not tenant.loyalty_live_enabled
            or not settings.FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED
            or not settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED
            or not settings.FIDELIZA_LEDGER_WRITES_ENABLED
            or not settings.FIDELIZA_POINTS_WRITES_ENABLED
            or not settings.FIDELIZA_TRUSTED_PAYMENT_ADAPTERS
            or not settings.FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED
            or not settings.FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED
            or not settings.FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED):
        raise PilotCouponBlocked("Piloto/cupom externo ainda bloqueado.")
    if NuvemshopCouponOwnershipIncident.objects.filter(
        tenant=tenant, intent__voucher__participant_id=voucher.participant_id,
        reviewed_at__isnull=True,
    ).exists():
        raise PilotCouponBlocked("Titularidade em revisão; novas emissões suspensas.")
    if voucher.state != LoyaltyVoucher.State.RESERVED or voucher.expires_at <= timezone.now():
        raise PilotCouponBlocked("Voucher não está reservado e válido.")
    if (not voucher.reward_id or "nuvemshop" not in voucher.allowed_channels.split(",")
            or voucher.reward.publication_status != "published"):
        raise PilotCouponBlocked("Recompensa não publicada para uso na Nuvemshop.")
    if getattr(settings, "FIDELIZA_PREISSUE_OWNERSHIP_CHECK_ENABLED", False):
        _assert_verified_preissue_owner(voucher)
    # Uma linha de LoyaltyVoucher por si só não comprova que houve débito.
    # Cada cupom precisa de alocação da reserva real de pontos/cashback.
    if voucher.unit == LoyaltyVoucher.Unit.POINTS:
        allocated = sum(voucher.point_allocations.values_list("amount", flat=True))
    else:
        allocated = sum(voucher.cashback_allocations.values_list("amount_cents", flat=True))
    if allocated != voucher.amount:
        raise PilotCouponBlocked("Voucher sem reserva financeira íntegra.")
    cfg = config()
    install = NuvemshopInstallation.objects.filter(
        tenant=tenant, store_id=tenant.external_store_id, client_id=cfg.client_id,
    ).first()
    if (not install or not {"read_orders", "write_coupons"} <= parse_scopes(install.scope)):
        raise PilotCouponBlocked("OAuth requer read_orders e write_coupons; reinstale o app.")
    return install, cfg


def provision_coupon(*, voucher_id, issued_code=None, opener=None):
    """Reserva intento no DB ANTES de chamar POST; GET reconcilia resultado incerto."""
    with transaction.atomic():
        voucher = LoyaltyVoucher.objects.select_related(
            "tenant", "reward",
        ).select_for_update(of=("self",)).get(pk=voucher_id)
        install, cfg = _context(voucher)
        intent = NuvemshopCouponIntent.objects.select_for_update().filter(voucher=voucher).first()
        new = intent is None
        if new:
            if (not isinstance(issued_code, str) or not
                any(secrets.compare_digest(voucher.code_digest, candidate)
                    for candidate in _code_digests(issued_code))):
                raise PilotCouponBlocked("Código de voucher não corresponde à emissão interna.")
            code = issued_code
            intent = NuvemshopCouponIntent.objects.create(
                tenant=voucher.tenant, voucher=voucher,
                store_id=install.store_id,
                code_sha256=hashlib.sha256(code.encode()).hexdigest(),
                encrypted_code=encrypt_token(code, cfg.token_keys),
            )
        else:
            code = decrypt_token(intent.encrypted_code, cfg.token_keys)
            if issued_code is not None and not secrets.compare_digest(code, issued_code):
                raise PilotCouponBlocked("Não é permitido trocar o código de cupom.")
            if intent.store_id != install.store_id:
                raise PilotCouponBlocked("Cupom pertence a outra instalação.")
            if intent.remote_coupon_id and intent.state in (
                NuvemshopCouponIntent.State.ISSUED,
                NuvemshopCouponIntent.State.APPLIED,
                NuvemshopCouponIntent.State.SETTLED,
            ):
                return intent, code
        expected = coupon_payload(
            code=code, discount_cents=voucher.discount_cents,
            min_order_cents=voucher.minimum_order_cents, expires_at=voucher.expires_at,
        )
        token = decrypt_token(install.token_ciphertext, cfg.token_keys)
    try:
        if new:
            remote_id = create_coupon_once(
                store_id=install.store_id, token=token,
                agent=cfg.user_agent, expected=expected, opener=opener,
            )
        else:
            remote_id = find_coupon_exact(
                store_id=install.store_id, token=token,
                agent=cfg.user_agent, expected=expected, opener=opener,
            )
            if remote_id is None:
                raise PilotCouponBlocked(
                    "Cupom não encontrado; resultado anterior incerto. Revisão manual, sem novo POST."
                )
    except (CouponRemoteError, PilotCouponBlocked) as exc:
        NuvemshopCouponIntent.objects.filter(pk=intent.pk).update(
            state=NuvemshopCouponIntent.State.UNCERTAIN,
        )
        raise PilotCouponBlocked(
            "Cupom externo não confirmado; reserva mantida, sem repetição automática."
        ) from None

    with transaction.atomic():
        locked = NuvemshopCouponIntent.objects.select_for_update().get(pk=intent.pk)
        if locked.remote_coupon_id and locked.remote_coupon_id != remote_id:
            raise PilotCouponBlocked("Cupom externo mudou de identificador.")
        locked.remote_coupon_id = remote_id
        if locked.state not in (locked.State.APPLIED, locked.State.SETTLED):
            locked.state = locked.State.ISSUED
        locked.save(update_fields=["remote_coupon_id", "state", "updated_at"])
        return locked, code
