"""Revogação verificável de cupons únicos Nuvemshop (API 2025-03).

DELETE sem retry; crédito só volta se GET antes do DELETE demonstrar used=0,
a remoção for confirmada por GET após DELETE, e não houver compra vinculada
com captura incerta. Não há compensação financeira inventada por webhook.
"""
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.loyalty.models import LoyaltyVoucher, FinancialEvidence
from apps.loyalty.services import LoyaltyBlocked, cancel_voucher
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant
from .coupon_client import CouponRemoteError, delete_coupon_once, get_coupon_by_id
from .models import NuvemshopCouponIntent, NuvemshopInstallation
from .scopes import parse_scopes
from .security import config, decrypt_token


class CouponRevokeBlocked(ValueError):
    pass


def _credentials(*, intent):
    if not getattr(settings, "FIDELIZA_NUVEMSHOP_COUPON_REVOCATION_ENABLED", False):
        raise CouponRevokeBlocked("Revogação externa está desativada.")
    tenant = intent.tenant
    if (tenant.status != Tenant.Status.ACTIVE
            or tenant.platform != "nuvemshop"
            or tenant.external_store_id != intent.store_id):
        raise CouponRevokeBlocked("Loja de origem inválida.")
    cfg = config()
    install = NuvemshopInstallation.objects.filter(
        tenant=tenant, store_id=intent.store_id, client_id=cfg.client_id,
    ).first()
    if not install or "write_coupons" not in parse_scopes(install.scope):
        raise CouponRevokeBlocked("OAuth com write_coupons necessário.")
    if not intent.remote_coupon_id:
        raise CouponRevokeBlocked("Cupom sem ID remoto confirmado; resolver outbox primeiro.")
    return cfg, decrypt_token(install.token_ciphertext, cfg.token_keys)


def _unused_snapshot(*, intent, remote, keys):
    if remote is None:
        # Ausência do cupom sem estado prévio não demonstra que não foi usado.
        if not intent.verified_unused_at:
            raise CouponRevokeBlocked("Ausência remota sem prova anterior de cupom não usado.")
        return False
    if (str(remote.get("id")) != intent.remote_coupon_id
            or remote.get("code") != decrypt_token(intent.encrypted_code, keys)):
        raise CouponRevokeBlocked("Cupom remoto não pertence ao voucher.")
    if type(remote.get("used")) is not int or remote["used"] != 0:
        raise CouponRevokeBlocked("Cupom pode ter sido usado no checkout.")
    return True


def revoke_coupon(*, intent_id, reason, opener=None, now=None):
    """Revogação em duas fases; GET de confirmação é obrigatório.

    Retorna (intent, reservation_cancelled). Nenhuma chamada usa CPF/PII
    nem recupera saldo de compra com prova de pagamento pendente.
    """
    now = now or timezone.now()
    if reason not in ("expired", "order_cancelled", "order_refunded"):
        raise CouponRevokeBlocked("Motivo de revogação inválido.")
    with transaction.atomic():
        base = NuvemshopCouponIntent.objects.select_related("tenant").get(pk=intent_id)
        Tenant.objects.select_for_update().get(pk=base.tenant_id)
        voucher = LoyaltyVoucher.objects.select_for_update().get(pk=base.voucher_id)
        intent = NuvemshopCouponIntent.objects.select_for_update().select_related(
            "tenant",
        ).get(pk=intent_id)
        if intent.state == intent.State.SETTLED or voucher.state == LoyaltyVoucher.State.REDEEMED:
            raise CouponRevokeBlocked("Cupom liquidado não pode ser revogado com devolução.")
        if intent.state == intent.State.REVOKED:
            return intent, _maybe_cancel_reservation(intent=intent, voucher=voucher, now=now)
        if intent.state not in (
            intent.State.ISSUED, intent.State.REVOKING, intent.State.REVOKE_UNKNOWN,
        ):
            raise CouponRevokeBlocked("Cupom não confirmado ou estado de origem desconhecido.")
        if reason == "expired":
            if voucher.expires_at + timedelta(minutes=30) > now or intent.order_id:
                raise CouponRevokeBlocked("Expiração exige carência de checkout e ausência de pedido.")
        else:
            if not intent.order_id:
                raise CouponRevokeBlocked("Cancelamento exige pedido externo vinculado.")
            sale = SaleRecord.objects.filter(
                tenant=intent.tenant, channel=SaleRecord.Channel.NUVEMSHOP,
                external_reference=intent.order_id,
                order_status__in=[
                    SaleRecord.OrderStatus.CANCELLED, SaleRecord.OrderStatus.REFUNDED,
                ],
            ).first()
            if sale is None:
                raise CouponRevokeBlocked("Pedido ainda não consta cancelado/estornado.")
        cfg, token = _credentials(intent=intent)
        intent.revoke_reason = reason
        if intent.state == intent.State.ISSUED:
            intent.state = intent.State.REVOKING
        intent.save(update_fields=["state", "revoke_reason", "updated_at"])
        store_id, remote_id, agent, keys = (
            intent.store_id, intent.remote_coupon_id, cfg.user_agent, cfg.token_keys
        )

    try:
        before = get_coupon_by_id(
            store_id=store_id, token=token, agent=agent,
            coupon_id=remote_id, opener=opener,
        )
        needs_delete = _unused_snapshot(
            intent=intent, remote=before, keys=keys,
        )
        if needs_delete:
            NuvemshopCouponIntent.objects.filter(pk=intent_id).update(
                verified_unused_at=now,
            )
            delete_coupon_once(
                store_id=store_id, token=token, agent=agent,
                coupon_id=remote_id, opener=opener,
            )
        after = get_coupon_by_id(
            store_id=store_id, token=token, agent=agent,
            coupon_id=remote_id, opener=opener,
        )
        if after is not None and not after.get("deleted_at"):
            raise CouponRevokeBlocked("DELETE ainda não confirmado por GET remoto.")
    except (CouponRemoteError, CouponRevokeBlocked):
        # Estado incerto: o saldo não volta; o operador pode reconsultar
        # sem repetir DELETE às cegas.
        NuvemshopCouponIntent.objects.filter(pk=intent_id).update(
            state=NuvemshopCouponIntent.State.REVOKE_UNKNOWN,
        )
        raise CouponRevokeBlocked(
            "Revogação não comprovada; reserva financeira continua bloqueada."
        ) from None
    with transaction.atomic():
        base = NuvemshopCouponIntent.objects.select_related("tenant").get(pk=intent_id)
        Tenant.objects.select_for_update().get(pk=base.tenant_id)
        voucher = LoyaltyVoucher.objects.select_for_update().get(pk=base.voucher_id)
        locked = NuvemshopCouponIntent.objects.select_for_update().get(pk=intent_id)
        if locked.state == locked.State.SETTLED or voucher.state == LoyaltyVoucher.State.REDEEMED:
            raise CouponRevokeBlocked("Pedido liquidado durante a revogação.")
        if locked.order_id != intent.order_id:
            raise CouponRevokeBlocked("Associação do pedido mudou durante a revogação.")
        locked.state = locked.State.REVOKED
        locked.revoked_at = timezone.now()
        locked.save(update_fields=["state", "revoked_at", "updated_at"])
        return locked, _maybe_cancel_reservation(intent=locked, voucher=voucher, now=now)


def _maybe_cancel_reservation(*, intent, voucher, now):
    """Só devolve reserva de cupom NÃO usado, vencido e sem pedido.

    Cancelamento de compra vinculada exige prova independente de NÃO captura;
    sem essa prova, a revogação externa é segura, mas o saldo fica reservado.
    """
    if voucher.state == LoyaltyVoucher.State.CANCELLED:
        return False
    if (intent.revoke_reason != "expired" or intent.order_id
            or voucher.expires_at + timedelta(minutes=30) > now
            or not intent.verified_unused_at
            or intent.state != intent.State.REVOKED):
        return False
    if not (settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED
            and settings.FIDELIZA_POINTS_WRITES_ENABLED
            and settings.FIDELIZA_LEDGER_WRITES_ENABLED):
        return False
    try:
        return cancel_voucher(tenant_id=intent.tenant_id, voucher_id=voucher.pk)
    except (PermissionError, LoyaltyBlocked):
        return False
