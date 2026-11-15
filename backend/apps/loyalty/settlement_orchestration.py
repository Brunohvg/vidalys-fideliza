"""PR26: prova PSP em QA e baixa transacional do voucher + nova concessão.

Duas fases: GET PSP externo sem lock; prova append-only idempotente; liquidação
do voucher + grant de nova compra em uma ÚNICA transação. A prova pode
permanecer auditada se os custos não liberarem concessão; repetir é seguro.
"""
from django.conf import settings
from django.db import transaction

from apps.nuvemshop.models import NuvemshopCouponIntent
from apps.nuvemshop.coupon_settlement import settle_coupon_after_psp_capture
from apps.sales.models import SaleRecord
from .payment_proof import (
    PaymentProofBlocked, verify_and_record_pagarme_capture, credit_verified_sale,
)
from .services import OrderCosts


class SettlementBlocked(ValueError):
    pass


def settle_qa_nuvemshop_checkout(*, intent_id, charge_id, costs, opener=None):
    """Proibido em lojas comerciais até PSP por tenant + checkout anti-fraude real.

    Não exposto via endpoint público. QA somente; exige validação de cliente
    feita no order_recheck_service (intent.state APPLIED).
    """
    if not (
        getattr(settings, "FIDELIZA_PAYMENT_PROOF_ENABLED", False)
        and getattr(settings, "FIDELIZA_PAYMENT_PROOF_STRICT_ORIGIN_ENABLED", False)
        and getattr(settings, "FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED", False)
        and getattr(settings, "FIDELIZA_POINTS_WRITES_ENABLED", False)
        and getattr(settings, "FIDELIZA_LEDGER_WRITES_ENABLED", False)
    ):
        raise SettlementBlocked("Liquidação financeira desativada.")
    if not isinstance(costs, OrderCosts):
        raise SettlementBlocked("Custos auditados obrigatórios.")
    intent = NuvemshopCouponIntent.objects.select_related("tenant", "voucher").get(pk=intent_id)
    if (
        not intent.tenant.loyalty_live_enabled
        or not intent.tenant.slug.startswith(("qa-", "homolog-"))
        or intent.state not in (intent.State.APPLIED, intent.State.SETTLED)
        or not intent.order_id
        or intent.voucher.tenant_id != intent.tenant_id
    ):
        raise SettlementBlocked("Cupom ou titular sem vínculo QA validado.")
    sale = SaleRecord.objects.select_related("customer_profile").filter(
        tenant=intent.tenant, channel=SaleRecord.Channel.NUVEMSHOP,
        external_reference=intent.order_id, order_status=SaleRecord.OrderStatus.PAID,
    ).first()
    if (
        sale is None
        or not sale.customer_profile
        or sale.customer_profile.participant_id != intent.voucher.participant_id
    ):
        raise SettlementBlocked("Compra não pertence ao titular do voucher.")
    # Reconsulta externa independente dentro da rotina autenticada e restrita
    # à loja QA pinada. Nunca aceitar 'charge' de um payload de View.
    try:
        evidence, _ = verify_and_record_pagarme_capture(
            sale_id=sale.pk, charge_id=charge_id, opener=opener,
        )
    except PaymentProofBlocked:
        raise SettlementBlocked("Prova PSP não verificada.") from None
    with transaction.atomic():
        locked = NuvemshopCouponIntent.objects.select_for_update().get(pk=intent.pk)
        if locked.state not in (locked.State.APPLIED, locked.State.SETTLED):
            raise SettlementBlocked("Cupom mudou de estado.")
        if locked.order_id != sale.external_reference:
            raise SettlementBlocked("Associação do cupom mudou.")
        coupon, redeemed_now = settle_coupon_after_psp_capture(
            intent_id=locked.pk, capture_evidence_id=evidence.pk,
        )
        grant, granted_now = credit_verified_sale(
            evidence_id=evidence.pk, costs=costs,
        )
        return {
            "voucher_id": str(coupon.voucher_id),
            "order_id": sale.external_reference,
            "redeemed_now": redeemed_now,
            "grant_id": str(grant.pk),
            "granted_now": granted_now,
            "financial_proof_id": str(evidence.pk),
        }
