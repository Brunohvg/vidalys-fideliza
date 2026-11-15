"""Revoke remote coupon before releasing source-attributed ledger reservations.

External DELETE is not transactional with PostgreSQL. The operation first
marks REVOKING, then verifies the provider by GET and records the result.
A timeout stays REVOKING until subsequent GET confirms it is unusable.
"""
from django.db import transaction
from django.utils import timezone
from apps.loyalty.models import FinancialEvidence, LoyaltyVoucher
from apps.loyalty.services import _cancel_reserved_voucher, LoyaltyBlocked
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant
from .coupon_client import CouponRemoteError, delete_coupon_once, inspect_coupon_by_id
from .models import (NuvemshopCouponIntent, NuvemshopCouponRevocationAudit,
                     NuvemshopInstallation)
from .scopes import parse_scopes
from .security import config, decrypt_token


class RevocationBlocked(ValueError):
    pass


def _eligibility(intent, reason):
    voucher = intent.voucher
    if voucher.state != LoyaltyVoucher.State.RESERVED:
        raise RevocationBlocked("Voucher já utilizado/cancelado")
    if intent.state == intent.State.SETTLED:
        raise RevocationBlocked("Voucher liquidado não pode ser revogado")
    if not intent.remote_coupon_id or intent.state in (
        intent.State.PREPARED, intent.State.UNCERTAIN,
    ):
        raise RevocationBlocked("ID externo não confirmado; conciliação necessária")
    if NuvemshopCouponRevocationAudit.objects.filter(intent=intent).exists():
        return
    if reason == "expired":
        if voucher.expires_at > timezone.now() or intent.order_id:
            raise RevocationBlocked("Voucher ainda válido ou associado a pedido")
    elif reason == "cancelled_unpaid":
        if not intent.order_id:
            raise RevocationBlocked("Pedido cancelado não identificado")
        sale = SaleRecord.objects.filter(
            tenant=intent.tenant, channel=SaleRecord.Channel.NUVEMSHOP,
            external_reference=intent.order_id,
            order_status__in=(
                SaleRecord.OrderStatus.CANCELLED,
                SaleRecord.OrderStatus.REFUNDED,
            ),
        ).first()
        if sale is None or FinancialEvidence.objects.filter(
            sale=sale, kind=FinancialEvidence.Kind.CAPTURE,
        ).exists():
            raise RevocationBlocked("Cancelamento ou ausência de captura não demonstrados")
    else:
        raise RevocationBlocked("Motivo de revogação inválido")


def revoke_and_release(*, intent_id, reason, opener=None):
    """Idempotent effect, but remote network uncertainty fails closed."""
    # All revocations of this tenant are serialized: no second caller can
    # cancel or settle a voucher while its remote state is unresolved.
    with transaction.atomic():
        base = NuvemshopCouponIntent.objects.select_related("tenant").get(pk=intent_id)
        Tenant.objects.select_for_update().get(pk=base.tenant_id)
        intent = NuvemshopCouponIntent.objects.select_for_update().select_related(
            "voucher", "tenant",
        ).get(pk=intent_id)
        existing = NuvemshopCouponRevocationAudit.objects.filter(intent=intent).first()
        if existing:
            if existing.reason != reason:
                raise RevocationBlocked("Motivo difere da revogação existente")
            if intent.voucher.state == LoyaltyVoucher.State.RESERVED:
                from apps.loyalty.services import _execution_enabled
                _execution_enabled()
                _cancel_reserved_voucher(intent.voucher)
            return intent, False
        _eligibility(intent, reason)
        cfg = config()
        installation = NuvemshopInstallation.objects.filter(
            tenant=intent.tenant, store_id=intent.store_id,
            client_id=cfg.client_id,
        ).first()
        if (installation is None
                or "write_coupons" not in parse_scopes(installation.scope)):
            raise RevocationBlocked("OAuth sem permissão de exclusão de cupom")
        token = decrypt_token(installation.token_ciphertext, cfg.token_keys)
        code = decrypt_token(intent.encrypted_code, cfg.token_keys)
        remote_id = intent.remote_coupon_id
        if intent.state != intent.State.REVOKING:
            intent.state = intent.State.REVOKING
            intent.save(update_fields=["state", "updated_at"])
    # GET verifies ownership and usage. If a previous DELETE timed out,
    # a missing/deleted coupon is accepted only for OUR previously stored ID.
    try:
        found = inspect_coupon_by_id(
            store_id=intent.store_id, token=token, agent=cfg.user_agent,
            remote_id=remote_id, opener=opener,
        )
        if found is not None:
            if found.get("code") != code:
                raise RevocationBlocked("Cupom remoto pertence a outro código")
            # A resposta pode informar valid=false porque o cupom JÁ FOI
            # consumido. Isso nunca autoriza devolver pontos por expiração.
            used = found.get("used")
            if type(used) is not int or used < 0 or used > 1:
                raise RevocationBlocked("Contagem de usos do cupom inconclusiva")
            if used and reason != "cancelled_unpaid":
                raise RevocationBlocked("Cupom já utilizado: revisão necessária")
            if found.get("valid") is True and found.get("deleted_at") is None:
                delete_coupon_once(
                    store_id=intent.store_id, token=token, agent=cfg.user_agent,
                    remote_id=remote_id, opener=opener,
                )
                found = inspect_coupon_by_id(
                    store_id=intent.store_id, token=token, agent=cfg.user_agent,
                    remote_id=remote_id, opener=opener,
                )
        if found is not None and (
            found.get("valid") is not False
            and found.get("deleted_at") is None
        ):
            raise RevocationBlocked("API ainda considera o cupom utilizável")
    except CouponRemoteError:
        raise RevocationBlocked("Revogação remota pendente de confirmação") from None

    # State change and compensation are atomic; if ledger is OFF, never
    # claim a successful local refund, even though remote may be deleted.
    with transaction.atomic():
        Tenant.objects.select_for_update().get(pk=intent.tenant_id)
        locked = NuvemshopCouponIntent.objects.select_for_update().select_related(
            "voucher",
        ).get(pk=intent.pk)
        if locked.remote_coupon_id != remote_id or locked.state not in (
            locked.State.REVOKING, locked.State.REVOKED,
        ):
            raise RevocationBlocked("Estado externo mudou durante revogação")
        from apps.loyalty.services import _execution_enabled
        _execution_enabled()
        locked.state = locked.State.REVOKED
        locked.save(update_fields=["state", "updated_at"])
        NuvemshopCouponRevocationAudit.objects.get_or_create(
            intent=locked,
            defaults={"tenant_id":locked.tenant_id,"remote_id":remote_id,"reason":reason},
        )
        try:
            _cancel_reserved_voucher(locked.voucher)
        except LoyaltyBlocked:
            raise RevocationBlocked("Reservas exigem conciliação") from None
        return locked, True
