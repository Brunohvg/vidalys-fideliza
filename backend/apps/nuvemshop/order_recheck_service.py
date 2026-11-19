"""Reconsulta de pedido Nuvemshop: ID do webhook => GET OAuth -> contrato unificado.

A plataforma relata payment_status, mas não prova captura PSP. Nenhuma função
aqui concede pontos, cashback ou marca LoyaltyVoucher como redeemed.
"""
import hashlib
import logging
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.channels.adapters.nuvemshop import ingest_nuvemshop_snapshot
from apps.customers.services import find_verified_customer, normalize_email, normalize_checkout_phone, normalize_cpf
from apps.loyalty.models import LoyaltyVoucher
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant
from .models import NuvemshopCouponIntent, NuvemshopInstallation, NuvemshopOrderRecheck
from .coupon_ownership import check_paid_coupon_ownership
from .order_readonly import (
    INTEGRATION_FIELDS, OrderReadError, read_order, safe_id, summarize_order,
)
from .order_webhook_models import OrderWebhookEvent
from .scopes import has_order_access
from .security import config, decrypt_token


logger = logging.getLogger(__name__)


class ClubRetry(RuntimeError):
    """Clube do site não processou o pedido: a tarefa repete (nunca marca "checked" por cima)."""


def _order_status(summary):
    from apps.sales.models import SaleRecord
    if summary["review_status"] in ("blocked_refund", "blocked_chargeback"):
        return SaleRecord.OrderStatus.REFUNDED
    if summary["order_status"] == "cancelled" or summary["review_status"] == "blocked_cancelled":
        return SaleRecord.OrderStatus.CANCELLED          # inclui pagamento anulado (voided)
    if summary["payment_status"] == "paid":
        return SaleRecord.OrderStatus.PAID
    return SaleRecord.OrderStatus.PENDING


def _run_club(*, event, tenant, order, grant=False, profile=None):
    """Clube no site em duas etapas da reconsulta:

    1) grant=False, logo após conferir loja e pedido: só BAIXAS (cupom do clube usado, estorno,
       devolução). Não depende de cadastro nem de titularidade: saldo já emitido não pode
       ficar sem baixa por um telefone mal digitado.
    2) grant=True, depois que identidade e titularidade passaram: concede o saldo novo.
       Contato contraditório ou violação de titularidade param antes e nada é concedido.

    Falha em qualquer etapa fica registrada (status "club_retry") e sobe para a tarefa repetir.
    """
    from apps.sales.models import CounterPilot
    if not CounterPilot.objects.filter(tenant=tenant).exists():
        return None
    summary = summarize_order(order, order_id=event.order_id)
    if summary["currency"] != "BRL":
        return None
    try:
        from apps.sales.online import handle_order
        with transaction.atomic():
            return handle_order(tenant=tenant, order=order, order_id=event.order_id,
                                status=_order_status(summary), total_cents=summary["reported_total_cents"],
                                profile=profile if grant else None, grant=grant)
    except Exception:
        NuvemshopOrderRecheck.objects.update_or_create(event=event, defaults={
            "status": "club_retry", "checked_at": timezone.now()})
        logger.warning("clube no site: pedido pendente de reprocessamento")
        raise ClubRetry("club_pending") from None


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
    """Never link a sale using one verified contact over a contradictory one.

    Unverified sales may still enter as provisional (no loyalty credit).
    Mixed verified+unknown or two different profiles require manual review.
    """
    customer = order.get("customer")
    customer = customer if isinstance(customer, dict) else {}
    checks = (
        (order.get("contact_email"), normalize_email, "email"),
        (customer.get("email"), normalize_email, "email"),
        (order.get("contact_phone"), normalize_checkout_phone, "phone_e164"),
        (customer.get("phone"), normalize_checkout_phone, "phone_e164"),
        (order.get("contact_identification"), normalize_cpf, "cpf"),
    )
    identities = []
    for raw, normalize, kind in checks:
        if raw is None or raw == "":
            continue
        if not isinstance(raw, str):
            raise RecheckBlocked("Identidade do comprador malformada")
        try:
            value = normalize(raw)
            profile = find_verified_customer(tenant_id=tenant.pk, **{kind: value})
        except ValueError:
            raise RecheckBlocked("Contato informado exige conferência manual") from None
        identities.append((value, profile, kind))
    profiles = {profile.pk for _, profile, _ in identities if profile is not None}
    if len(profiles) > 1 or (profiles and any(p is None for _, p, _ in identities)):
        raise RecheckBlocked("Contatos do checkout não pertencem ao mesmo perfil verificado")
    # CPF alone is not a safe key for legacy order ingestion, whose channels
    # accept only normalized email/phone as customer_identifier.
    contact = next((row for row in identities if row[2] in ("email", "phone_e164")), None)
    if contact is None:
        return None, None
    return contact[0], contact[1]


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
        (order.get("contact_phone"), normalize_checkout_phone, "phone_e164"),
        (buyer.get("phone"), normalize_checkout_phone, "phone_e164"),
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
        Tenant.objects.select_for_update().get(
            pk=event.tenant_id, status=Tenant.Status.ACTIVE)
        locked = NuvemshopCouponIntent.objects.select_for_update().select_related(
            "voucher",
        ).get(pk=intent.pk)
        # The external read can race with remote revocation/settlement:
        # validate the locked CURRENT state, never trust the earlier snapshot.
        if locked.state == locked.State.SETTLED:
            return "already_settled"
        if (locked.state not in (locked.State.ISSUED, locked.State.APPLIED)
                or locked.voucher.state != LoyaltyVoucher.State.RESERVED
                or locked.voucher.participant_id != profile.participant_id):
            raise RecheckBlocked("Cupom alterado durante reconsulta")
        if locked.order_id and locked.order_id != event.order_id:
            raise RecheckBlocked("Cupom de outro pedido")
        locked.order_id = event.order_id
        locked.state = NuvemshopCouponIntent.State.APPLIED
        locked.save(update_fields=["order_id", "state", "updated_at"])
    return "applied_pending_independent_capture"


def recheck_order_event(*, event_id, opener=None, pause=None, reprocess=False):
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
    # reprocess: crédito desde a adesão relê um pedido já conferido pelo MESMO caminho
    # (tudo aqui é idempotente: baixa, concessão e ingestão não se repetem).
    if existing and existing.status == "checked" and not reprocess:
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
    _run_club(event=event, tenant=tenant, order=order)
    incident = check_paid_coupon_ownership(event=event, order=order, cfg=cfg)
    if incident in ("ownership_violation","requires_review"):
        NuvemshopOrderRecheck.objects.update_or_create(event=event, defaults={
            "status": "ownership_violation" if incident == "ownership_violation"
                      else "needs_review",
            "checked_at": timezone.now(),
        })
        # An external discount may have been consumed, but ZERO loyalty
        # points/cashback are issued to either shopper or voucher issuer.
        return incident
    # Clube no site, etapa 2: titularidade conferida -> concede com a regra de identidade do
    # CLUBE (e-mail confirmado + celular que não desminta). Não depende da conferência estrita
    # de contatos do motor antigo logo abaixo, que recusa telefone sem +55.
    _run_club(event=event, tenant=tenant, order=order, grant=True)
    identity, profile = _buyer_identity(order, tenant)
    summary = summarize_order(order, order_id=event.order_id,
                              participant_verified=profile is not None)
    if summary["currency"] != "BRL":
        raise RecheckBlocked("Somente BRL pode ser normalizado")
    status = _order_status(summary)
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
