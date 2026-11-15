"""Reconsulta de pedido Nuvemshop: ID do webhook => GET OAuth -> contrato unificado.

A plataforma relata payment_status, mas não prova captura PSP. Nenhuma função
aqui concede pontos, cashback ou marca LoyaltyVoucher como redeemed.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.channels.adapters.nuvemshop import ingest_nuvemshop_snapshot
from apps.customers.services import find_verified_customer, normalize_email, normalize_phone, normalize_cpf
from apps.loyalty.models import LoyaltyVoucher
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant
from .models import NuvemshopCouponIntent, NuvemshopInstallation, NuvemshopOrderRecheck
from .order_readonly import (
    INTEGRATION_FIELDS, OrderReadError, read_order, safe_id, summarize_order,
)
from .order_webhook_models import OrderWebhookEvent
from .scopes import has_order_access
from .security import config, decrypt_token


class RecheckBlocked(ValueError):
    pass


def _cents(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise RecheckBlocked("Valor monetário do cupom inválido") from None
    if not number.is_finite() or number < 0 or number > 1_000_000:
        raise RecheckBlocked("Valor monetário fora dos limites")
    if number * 100 != (number * 100).to_integral_value():
        raise RecheckBlocked("Valor monetário deve ter centavos exatos")
    return int(number * 100)


def _buyer_identity(order, tenant):
    """O pedido não recebe consentimento novo por ter um contato no checkout."""
    identities = []
    for name, normalize, kw in (
        ("contact_email", normalize_email, "email"),
        ("contact_phone", normalize_phone, "phone_e164"),
    ):
        raw = order.get(name)
        if isinstance(raw, str) and raw.strip():
            try:
                identity = normalize(raw)
                profile = find_verified_customer(tenant_id=tenant.pk, **{kw: identity})
                identities.append((identity, profile))
            except ValueError:
                continue
    verified = {p.pk for _, p in identities if p is not None}
    if len(verified) > 1:
        raise RecheckBlocked("Pedido contém contatos comprovados de pessoas diferentes")
    # Se existem dois contatos diferentes e apenas um verificado, utilizar
    # o verificado; nenhum outro contato é associado à carteira.
    for identity, profile in identities:
        if profile is not None:
            return identity, profile
    return (identities[0][0], None) if identities else (None, None)


def _paid_coupon_from_order(*, event, order, sale, profile):
    if event.topic != OrderWebhookEvent.Topic.PAID:
        return "not_paid_event"
    if not (event.tenant.loyalty_live_enabled
            and order.get("payment_status") == "paid"
            and order.get("status") != "cancelled"
            and profile is not None and profile.participant_id):
        return "not_eligible_for_coupon_match"
    remote_coupon_id = safe_id(order.get("coupon_id"))
    coupons = order.get("coupon")
    if remote_coupon_id is None or not isinstance(coupons, list):
        return "coupon_identity_missing"
    codes = [x.get("code") for x in coupons if isinstance(x, dict)
             and safe_id(x.get("id")) == remote_coupon_id]
    if len(codes) != 1 or not isinstance(codes[0], str):
        return "coupon_details_not_matched"
    intent = NuvemshopCouponIntent.objects.select_related(
        "voucher", "tenant",
    ).filter(
        tenant=event.tenant, store_id=event.store_id,
        remote_coupon_id=remote_coupon_id,
    ).first()
    if intent is None:
        return "coupon_not_ours"
    # Coupon ownership is stricter than ordinary order ingestion:
    # every supplied checkout contact MUST independently identify the
    # same previously verified customer. A phone match cannot override
    # a different/unverified checkout email or vice versa.
    buyer = order.get("customer")
    buyer = buyer if isinstance(buyer, dict) else {}
    checks = (
        (order.get("contact_email"), normalize_email, "email"),
        (buyer.get("email"), normalize_email, "email"),
        (order.get("contact_phone"), normalize_phone, "phone_e164"),
        (buyer.get("phone"), normalize_phone, "phone_e164"),
        (order.get("contact_identification"), normalize_cpf, "cpf"),
    )
    confirmed = 0
    for raw, normalize, field in checks:
        if raw is None or raw == "":
            continue
        if not isinstance(raw, str):
            raise RecheckBlocked("Identificação do comprador inválida")
        try:
            identity = normalize(raw)
            exact = find_verified_customer(tenant_id=event.tenant_id, **{field: identity})
        except ValueError:
            raise RecheckBlocked("Contato do checkout não confirmado") from None
        if exact is None or exact.pk != profile.pk:
            raise RecheckBlocked("Cupom pertence a outro comprador")
        confirmed += 1
    if not confirmed:
        raise RecheckBlocked("Não foi possível validar titularidade no checkout")
    if (intent.state not in (
        NuvemshopCouponIntent.State.ISSUED,
        NuvemshopCouponIntent.State.APPLIED,
        NuvemshopCouponIntent.State.SETTLED,
    ) or intent.voucher.participant_id != profile.participant_id
            or intent.voucher.state == LoyaltyVoucher.State.CANCELLED):
        raise RecheckBlocked("Cupom/identidade não autorizados")
    cfg = config()
    expected = decrypt_token(intent.encrypted_code, cfg.token_keys)
    if codes[0] != expected:
        raise RecheckBlocked("Código divergente do cupom emitido")
    discount = _cents(order.get("discount_coupon"))
    if discount != intent.voucher.discount_cents:
        raise RecheckBlocked("Desconto aplicado não corresponde ao voucher")
    amount_after_discount = _cents(order.get("total"))
    if amount_after_discount + discount < intent.voucher.minimum_order_cents:
        raise RecheckBlocked("Pedido não cumpre o mínimo da recompensa")
    if intent.order_id and intent.order_id != event.order_id:
        raise RecheckBlocked("Cupom associado a outro pedido")
    if intent.state == NuvemshopCouponIntent.State.SETTLED:
        return "already_settled"
    # Esta escrita NÃO é uma baixa do ledger. Apenas marca aplicação reportada
    # pela plataforma; a conciliação independente precisa chamar settle_coupon.
    with transaction.atomic():
        locked = NuvemshopCouponIntent.objects.select_for_update().get(pk=intent.pk)
        if locked.order_id and locked.order_id != event.order_id:
            raise RecheckBlocked("Cupom de outro pedido")
        locked.order_id = event.order_id
        locked.state = NuvemshopCouponIntent.State.APPLIED
        locked.save(update_fields=["order_id", "state", "updated_at"])
    return "applied_pending_independent_capture"


def recheck_order_event(*, event_id, opener=None, pause=None):
    """Consulta exclusiva do serviço servidor; reexecutável por inbox idempotente."""
    if not (settings.FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED
            and settings.FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED
            and getattr(settings, "FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED", False)):
        raise RecheckBlocked("Reconsulta OAuth está desligada.")
    event = OrderWebhookEvent.objects.select_related("tenant").get(pk=event_id)
    tenant = event.tenant
    if (tenant.status != Tenant.Status.ACTIVE
            or tenant.platform != "nuvemshop"
            or tenant.external_store_id != event.store_id):
        raise RecheckBlocked("Webhook não corresponde à instalação ativa")
    cfg = config()
    installed = NuvemshopInstallation.objects.filter(
        tenant=tenant, store_id=event.store_id, client_id=cfg.client_id,
    ).first()
    if not installed or not has_order_access(installed.scope, preview_enabled=True):
        raise RecheckBlocked("Escopo read_orders ausente")
    existing = NuvemshopOrderRecheck.objects.filter(event=event).first()
    if existing and existing.status == "checked":
        return "already_checked"
    kwargs = {"opener": opener}
    if pause is not None:
        kwargs["pause"] = pause
    order = read_order(
        store_id=event.store_id, order_id=event.order_id,
        access_token=decrypt_token(installed.token_ciphertext, cfg.token_keys),
        user_agent=cfg.user_agent, fields=INTEGRATION_FIELDS, **kwargs,
    )
    if safe_id(order.get("id")) != event.order_id or (
        order.get("store_id") is not None
        and safe_id(order["store_id"]) != event.store_id
    ):
        raise RecheckBlocked("OAuth retornou pedido de outra loja")
    identity, profile = _buyer_identity(order, tenant)
    summary = summarize_order(order, order_id=event.order_id,
                              participant_verified=profile is not None)
    if summary["currency"] != "BRL":
        raise RecheckBlocked("Somente BRL pode ser normalizado")
    if summary["review_status"] in ("blocked_refund", "blocked_chargeback"):
        status = SaleRecord.OrderStatus.REFUNDED
    elif summary["order_status"] == "cancelled":
        status = SaleRecord.OrderStatus.CANCELLED
    elif summary["payment_status"] == "paid":
        status = SaleRecord.OrderStatus.PAID
    else:
        status = SaleRecord.OrderStatus.PENDING
    if not identity:
        NuvemshopOrderRecheck.objects.update_or_create(event=event, defaults={
            "status": "needs_identity", "checked_at": timezone.now(),
        })
        return "needs_identity"
    cents = summary["reported_total_cents"]
    if status in (SaleRecord.OrderStatus.PAID, SaleRecord.OrderStatus.PENDING) and cents == 0:
        raise RecheckBlocked("Pedido não possui valor positivo")
    normalized = {
        "external_order_id": event.order_id,
        "customer_identifier": identity,
        "total_amount": f"{cents // 100}.{cents % 100:02d}",
        "currency": "BRL", "status": status,
        "source_event_id": "nuv-" + event.id.hex,
        "occurred_at": event.received_at.isoformat(),
    }
    result = ingest_nuvemshop_snapshot(
        tenant_id=tenant.pk, store_id=event.store_id, normalized_snapshot=normalized,
    )
    coupon_result = _paid_coupon_from_order(
        event=event, order=order, sale=result.sale, profile=profile,
    )
    if (status in (SaleRecord.OrderStatus.CANCELLED, SaleRecord.OrderStatus.REFUNDED)
            and tenant.loyalty_live_enabled
            and settings.FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED
            and settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED):
        # Only a previously matched coupon for THIS order can be revoked.
        # A cancelled checkout never substitutes PSP refund evidence.
        from .coupon_revocation import revoke_and_release
        candidate = NuvemshopCouponIntent.objects.filter(
            tenant=tenant, store_id=event.store_id,
            order_id=event.order_id, state__in=(
                NuvemshopCouponIntent.State.APPLIED,
                NuvemshopCouponIntent.State.REVOKING,
            ),
        ).first()
        if candidate is not None:
            revoke_and_release(intent_id=candidate.pk,
                               reason="cancelled_unpaid")
            coupon_result = "coupon_revoked_and_reservation_released"
    digest = hashlib.sha256(json.dumps({
        "tenant": str(tenant.pk), "order": event.order_id, "status": status,
        "amount": cents, "identity_verified": bool(profile),
        "coupon_result": coupon_result,
    }, sort_keys=True).encode()).hexdigest()
    NuvemshopOrderRecheck.objects.update_or_create(event=event, defaults={
        "status": "checked", "summary_digest": digest,
        "checked_at": timezone.now(),
    })
    return coupon_result
