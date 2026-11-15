"""Baixa financeira separada do webhook da Nuvemshop.

O webhook order/paid e GET OAuth são fatos da plataforma, não `FinancialEvidence`
do PSP. Só o adaptador autorizado pode chamar esta rotina com prova autenticada.
"""
from django.conf import settings
from django.db import transaction

from apps.loyalty.models import FinancialEvidence, VerifiedPaymentProof, LoyaltyVoucher
from apps.tenants.models import Tenant
from apps.loyalty.services import LoyaltyBlocked, redeem_voucher
from apps.sales.models import SaleRecord
from .models import NuvemshopCouponIntent
from .security import config, decrypt_token


class CouponSettlementBlocked(ValueError):
    pass


@transaction.atomic
def settle_coupon_after_psp_capture(*, intent_id, capture_evidence_id):
    if not (settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED
            and settings.FIDELIZA_POINTS_WRITES_ENABLED
            and settings.FIDELIZA_LEDGER_WRITES_ENABLED):
        raise CouponSettlementBlocked("Execução financeira desligada.")
    # Lock order matches revocation and ledger: tenant -> intent -> voucher.
    # Intent-first would deadlock against concurrent revocation.
    base = NuvemshopCouponIntent.objects.only("tenant_id").get(pk=intent_id)
    Tenant.objects.select_for_update().get(
        pk=base.tenant_id, status=Tenant.Status.ACTIVE,
    )
    intent = NuvemshopCouponIntent.objects.select_for_update().select_related(
        "tenant", "voucher",
    ).get(pk=intent_id, tenant_id=base.tenant_id)
    if (not intent.tenant.loyalty_live_enabled
            or not intent.order_id
            or intent.state not in (intent.State.APPLIED, intent.State.SETTLED)):
        raise CouponSettlementBlocked("Cupom sem uso confirmado e loja piloto autorizada.")
    sale = SaleRecord.objects.filter(
        tenant=intent.tenant, channel=SaleRecord.Channel.NUVEMSHOP,
        external_reference=intent.order_id,
        order_status=SaleRecord.OrderStatus.PAID,
    ).first()
    if sale is None:
        raise CouponSettlementBlocked("Pedido não encontrado ou não pago.")
    evidence = FinancialEvidence.objects.filter(
        pk=capture_evidence_id, tenant=intent.tenant, sale=sale,
        kind=FinancialEvidence.Kind.CAPTURE,
    ).first()
    if evidence is None:
        raise CouponSettlementBlocked("Prova PSP independente inexistente.")
    if (evidence.provider != "pagarme_v5" or not
            VerifiedPaymentProof.objects.filter(
                evidence=evidence, tenant=intent.tenant,
                proof_method="pagarme_v5_get",
            ).exists()):
        raise CouponSettlementBlocked("Evidência sem verificação PSP autenticada.")
    code = decrypt_token(intent.encrypted_code, config().token_keys)
    reference = f"nuvemshop:{intent.store_id}:{intent.order_id}"
    try:
        voucher, changed = redeem_voucher(
            tenant_id=intent.tenant_id, code=code, channel=SaleRecord.Channel.NUVEMSHOP,
            external_receipt=reference, sale_id=sale.pk,
            capture_evidence_id=evidence.pk,
        )
    except (LoyaltyBlocked, PermissionError):
        raise CouponSettlementBlocked("O pedido não atende aos requisitos de baixa.") from None
    if voucher.pk != intent.voucher_id:
        raise CouponSettlementBlocked("Voucher divergente do cupom emitido.")
    if intent.state != intent.State.SETTLED:
        intent.state = intent.State.SETTLED
        intent.save(update_fields=["state", "updated_at"])
    return intent, changed
