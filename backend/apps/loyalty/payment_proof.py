"""Authorized payment-proof adapters, never raw order/paid assertions.

No public HTTP view calls these adapters. QA tests use isolated secret values;
a real merchant requires a verified per-tenant PSP binding first.
"""
import hashlib
import hmac
import os
import re
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.loyalty.models import CashClosing, FinancialEvidence, VerifiedPaymentProof, VerifiedPspFeeReceipt
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant, TenantMembership
from apps.nuvemshop.pagarme_payment import fetch_charge, validate_paid_charge, PaymentProviderError
from apps.nuvemshop.pagarme_payables import fetch_payables, verify_payables

RECEIPT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$")


class PaymentProofBlocked(ValueError):
    pass


def _gate(tenant):
    if not getattr(settings, "FIDELIZA_PAYMENT_PROOF_RECORDING_ENABLED", False):
        raise PaymentProofBlocked("Comprovação financeira indisponível")
    if tenant.status != Tenant.Status.ACTIVE or not tenant.loyalty_live_enabled:
        raise PaymentProofBlocked("Loja não habilitada para comprovação")


def _digest(*parts):
    body = "|".join(map(str, parts)).encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode(), body, hashlib.sha256).hexdigest()


def _record(*, sale, provider, reference, paid_at, proof_method, operator=None):
    """Call under a tenant row lock. Corroborating evidence is immutable."""
    if (sale.order_status != SaleRecord.OrderStatus.PAID
            or not sale.reported_total_cents or timezone.is_naive(paid_at)
            or paid_at > timezone.now() + timedelta(minutes=5)):
        raise PaymentProofBlocked("Pedido ou data incompatível")
    reference_key = f"{proof_method}:{reference}"
    existing = FinancialEvidence.objects.filter(
        tenant=sale.tenant, provider=provider, external_event_id=reference_key,
    ).first()
    if existing:
        if (existing.sale_id != sale.pk
                or existing.amount_cents != sale.reported_total_cents
                or existing.occurred_at != paid_at
                or not VerifiedPaymentProof.objects.filter(
                    evidence=existing, tenant=sale.tenant, proof_method=proof_method,
                ).exists()):
            raise PaymentProofBlocked("Comprovação já usada com dados divergentes")
        return existing, False
    evidence = FinancialEvidence.objects.create(
        tenant=sale.tenant, sale=sale, provider=provider,
        external_event_id=reference_key,
        kind=FinancialEvidence.Kind.CAPTURE,
        amount_cents=sale.reported_total_cents,
        verification_digest=_digest(sale.tenant_id, sale.pk, provider,
                                   reference, paid_at.isoformat(), sale.reported_total_cents),
        occurred_at=paid_at, verified_at=timezone.now(),
    )
    VerifiedPaymentProof.objects.create(
        evidence=evidence, tenant=sale.tenant, proof_method=proof_method,
        reference_digest=_digest("proof", reference),
        operator=operator, captured_at=paid_at,
    )
    return evidence, True


def confirm_pagarme_charge(*, sale_id, charge_id, opener=None):
    """Verify an actual charge via Pagar.me Basic-auth GET, fixed HTTPS host.

    The PSP secret is bound to ONE tenant via secret-manager environment.
    This excludes cross-merchant charge lookups and wrong-tenant replay.
    """
    # PSP GET must happen OUTSIDE database locks: network latency would
    # otherwise hold the tenant lock and block checkout/ledger transactions.
    sale_ref = SaleRecord.objects.select_related("tenant").get(pk=sale_id)
    _gate(sale_ref.tenant)
    if sale_ref.channel not in (SaleRecord.Channel.NUVEMSHOP,
                                SaleRecord.Channel.VIDALYS_FLOW):
        raise PaymentProofBlocked("Provedor não corresponde ao canal")
    if str(sale_ref.tenant_id) != os.getenv("FIDELIZA_PAGARME_BOUND_TENANT_ID", ""):
        raise PaymentProofBlocked("Chave PSP não vinculada a esta loja")
    key = os.getenv("FIDELIZA_PAGARME_SECRET_KEY", "")
    if not key:
        raise PaymentProofBlocked("Chave PSP não instalada")
    try:
        charge = fetch_charge(charge_id=charge_id, secret_key=key, opener=opener)
        captured = validate_paid_charge(
            charge=charge, charge_id=charge_id,
            order_reference=sale_ref.external_reference,
            total_cents=sale_ref.reported_total_cents,
        )
    except PaymentProviderError as exc:
        raise PaymentProofBlocked(str(exc)) from None
    if captured > timezone.now() + timedelta(minutes=5):
        raise PaymentProofBlocked("PSP com captura futura")
    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(pk=sale_ref.tenant_id)
        _gate(tenant)
        # Re-read the sale under the same tenant lock to reject changes while
        # the remote PSP request was in flight.
        sale = SaleRecord.objects.select_for_update().get(pk=sale_id, tenant=tenant)
        if sale.channel not in (SaleRecord.Channel.NUVEMSHOP,
                                 SaleRecord.Channel.VIDALYS_FLOW):
            raise PaymentProofBlocked("Canal alterado após consulta PSP")
        try:
            validate_paid_charge(
                charge=charge, charge_id=charge_id,
                order_reference=sale.external_reference,
                total_cents=sale.reported_total_cents,
            )
        except PaymentProviderError as exc:
            raise PaymentProofBlocked(str(exc)) from None
        return _record(sale=sale, provider="pagarme_v5",
                       reference=charge_id, paid_at=captured,
                       proof_method="pagarme_v5_get")



def confirm_pagarme_financial_fees(*, evidence_id, charge_id, recipient_id=None,
                                  charge_opener=None, payables_opener=None):
    """Independently reconfirm charge + complete payables before atomic receipt.

    The existing PSP proof alone does not establish costs. This operation
    intentionally fails closed if payables are incomplete or not liquidated.
    No external HTTP is performed while holding tenant locks.
    """
    proof_ref = VerifiedPaymentProof.objects.select_related(
        "tenant","evidence__sale",
    ).get(evidence_id=evidence_id)
    sale_ref = proof_ref.evidence.sale
    _gate(proof_ref.tenant)
    if (proof_ref.proof_method != "pagarme_v5_get"
            or proof_ref.evidence.provider != "pagarme_v5"
            or proof_ref.reference_digest != _digest("proof", charge_id)
            or sale_ref.channel != SaleRecord.Channel.NUVEMSHOP):
        raise PaymentProofBlocked("Cobrança não vinculada à prova financeira")
    if str(sale_ref.tenant_id) != os.getenv("FIDELIZA_PAGARME_BOUND_TENANT_ID", ""):
        raise PaymentProofBlocked("PSP não vinculado à loja")
    bound_recipient = os.getenv("FIDELIZA_PAGARME_RECIPIENT_ID", "")
    if not bound_recipient or (recipient_id is not None and recipient_id != bound_recipient):
        raise PaymentProofBlocked("Recebedor PSP não autenticado")
    key = os.getenv("FIDELIZA_PAGARME_SECRET_KEY", "")
    if not key:
        raise PaymentProofBlocked("Chave PSP indisponível")
    try:
        charge = fetch_charge(
            charge_id=charge_id,secret_key=key,opener=charge_opener,
        )
        captured = validate_paid_charge(
            charge=charge,charge_id=charge_id,
            order_reference=sale_ref.external_reference,
            total_cents=sale_ref.reported_total_cents,
        )
        payables = fetch_payables(
            charge_id=charge_id,secret_key=key,opener=payables_opener,
        )
        fees = verify_payables(
            payables=payables,charge_id=charge_id,
            captured_cents=sale_ref.reported_total_cents,
            recipient_id=bound_recipient,
        )
    except PaymentProviderError as exc:
        raise PaymentProofBlocked(str(exc)) from None
    if captured != proof_ref.captured_at:
        raise PaymentProofBlocked("Momento da captura difere do recibo PSP")
    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(pk=proof_ref.tenant_id)
        _gate(tenant)
        proof = VerifiedPaymentProof.objects.select_for_update().select_related(
            "evidence__sale",
        ).get(pk=proof_ref.pk,tenant=tenant)
        sale = proof.evidence.sale
        if (sale.pk != sale_ref.pk
                or sale.order_status != SaleRecord.OrderStatus.PAID
                or sale.reported_total_cents != fees.gross_cents
                or proof.reference_digest != _digest("proof", charge_id)):
            raise PaymentProofBlocked("Venda, prova ou valor mudaram após GET PSP")
        expected_charge_digest = _digest("fee-charge",tenant.pk,charge_id)
        previous = VerifiedPspFeeReceipt.objects.filter(proof=proof).first()
        if previous:
            if (previous.charge_digest != expected_charge_digest
                    or previous.payables_digest != fees.snapshot_digest
                    or previous.fee_cents != fees.fee_cents
                    or previous.net_cents != fees.net_cents):
                raise PaymentProofBlocked("Tarifa da captura foi alterada")
            return previous, False
        return VerifiedPspFeeReceipt.objects.create(
            tenant=tenant, proof=proof, charge_digest=expected_charge_digest,
            payables_digest=fees.snapshot_digest,
            gross_cents=fees.gross_cents, fee_cents=fees.fee_cents,
            net_cents=fees.net_cents, payable_count=fees.count,
        ), True



@transaction.atomic
def attest_cash_close(*, sale_id, operator, external_receipt, closed_at):
    """Only an authenticated owner/admin of a physical/Flow tenant closes cash.

    This is an operator attestation, NOT bank/PSP settlement; a real launch
    requires auditable receipts and the financial global gates to be approved.
    """
    if not getattr(operator, "is_authenticated", False) or not operator.is_active:
        raise PaymentProofBlocked("Operador não autenticado")
    if not isinstance(external_receipt, str) or not RECEIPT_RE.fullmatch(external_receipt):
        raise PaymentProofBlocked("Recibo de fechamento inválido")
    if (timezone.is_naive(closed_at) or closed_at > timezone.now()
            or closed_at < timezone.now() - timedelta(days=30)):
        raise PaymentProofBlocked("Horário de fechamento fora da janela")
    sale_ref = SaleRecord.objects.get(pk=sale_id)
    tenant = Tenant.objects.select_for_update().get(pk=sale_ref.tenant_id)
    _gate(tenant)
    if sale_ref.channel not in (SaleRecord.Channel.COUNTER, SaleRecord.Channel.VIDALYS_FLOW):
        raise PaymentProofBlocked("Canal não permite fechamento de caixa")
    membership = TenantMembership.objects.filter(
        tenant=tenant, user=operator,
        role__in=(TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN),
    ).first()
    if membership is None:
        raise PaymentProofBlocked("Operador não administra esta loja")
    sale = SaleRecord.objects.get(pk=sale_id, tenant=tenant)
    existing = CashClosing.objects.filter(
        tenant=tenant, external_receipt=external_receipt,
    ).first()
    if existing and (existing.operator_id != operator.pk
                     or existing.amount_cents != sale.reported_total_cents
                     or existing.closed_at != closed_at):
        raise PaymentProofBlocked("Fechamento já pertence a outra operação")
    if not existing:
        existing = CashClosing.objects.create(
            tenant=tenant, operator=operator, external_receipt=external_receipt,
            amount_cents=sale.reported_total_cents, closed_at=closed_at,
        )
    return _record(sale=sale, provider="cash_close",
                   reference=f"{existing.pk}", paid_at=closed_at,
                   proof_method="cash_close", operator=operator)


def apply_verified_capture(*, evidence_id, costs=None, coupon_intent_id=None,
                           payment_fee_cents=None, opener=None):
    """Credit only after trusted PSP proof + authenticated per-line order costs.

    Merchant-supplied OrderCosts never authorize Nuvemshop credit. The remote
    OAuth read is performed before acquiring database row locks.
    """
    if not (settings.FIDELIZA_POINTS_WRITES_ENABLED
            and settings.FIDELIZA_LEDGER_WRITES_ENABLED
            and settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED):
        raise PaymentProofBlocked("Ledger financeiro desligado")
    if not getattr(settings, "FIDELIZA_ORDER_LINE_COST_BINDING_VERIFIED", False):
        raise PaymentProofBlocked("Linhas, quantidades, frete e descontos ainda não conciliados")
    source = VerifiedPaymentProof.objects.select_related("evidence__sale__tenant").get(
        evidence_id=evidence_id,
    )
    evidence = source.evidence
    if evidence.provider not in settings.FIDELIZA_TRUSTED_PAYMENT_ADAPTERS:
        raise PaymentProofBlocked("Provedor não aprovado para execução")
    verified_costs = costs
    if evidence.sale.channel == SaleRecord.Channel.NUVEMSHOP:
        if source.proof_method != "pagarme_v5_get" or evidence.provider != "pagarme_v5":
            raise PaymentProofBlocked("Prova PSP não autenticada")
        if not getattr(settings, "FIDELIZA_PSP_FEE_RECONCILIATION_VERIFIED", False):
            raise PaymentProofBlocked("Conciliação financeira PSP não homologada")
        fee_receipt = VerifiedPspFeeReceipt.objects.filter(
            proof=source, tenant=source.tenant_id,
        ).first()
        if (fee_receipt is None
                or fee_receipt.gross_cents != evidence.amount_cents
                or fee_receipt.net_cents + fee_receipt.fee_cents != fee_receipt.gross_cents
                or (payment_fee_cents is not None
                    and payment_fee_cents != fee_receipt.fee_cents)):
            raise PaymentProofBlocked("Tarifa PSP autenticada ausente ou divergente")
        payment_fee_cents = fee_receipt.fee_cents
        from apps.costs.order_item_cost_reconciliation import (
            read_verified_nuvemshop_order_costs, OrderItemCostBlocked,
        )
        try:
            verified_costs = read_verified_nuvemshop_order_costs(
                sale=evidence.sale,payment_fee_cents=payment_fee_cents,opener=opener,
            )
        except OrderItemCostBlocked:
            raise PaymentProofBlocked("Custo ou descontos por SKU não conciliados") from None

    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(pk=source.tenant_id)
        _gate(tenant)
        proof = VerifiedPaymentProof.objects.select_related(
            "evidence__sale",
        ).get(evidence_id=evidence_id,tenant=tenant)
        proof_evidence = proof.evidence
        if proof_evidence.sale.channel == SaleRecord.Channel.NUVEMSHOP:
            locked_fee = VerifiedPspFeeReceipt.objects.get(
                proof=proof,tenant=tenant,
            )
            if (locked_fee.fee_cents != verified_costs.costs.payment_fee_cents
                    or locked_fee.gross_cents != proof_evidence.amount_cents):
                raise PaymentProofBlocked("Recibo PSP mudou durante conciliação")
        if (proof_evidence.tenant_id != tenant.pk
                or proof_evidence.sale.tenant_id != tenant.pk
                or proof_evidence.provider not in settings.FIDELIZA_TRUSTED_PAYMENT_ADAPTERS
                or proof_evidence.kind != FinancialEvidence.Kind.CAPTURE
                or proof_evidence.sale.order_status != SaleRecord.OrderStatus.PAID):
            raise PaymentProofBlocked("Prova foi alterada ou pedido não elegível")
        from apps.loyalty.services import grant_for_captured_sale
        grant, created = grant_for_captured_sale(
            sale_id=proof_evidence.sale_id,
            evidence_id=proof_evidence.pk, costs=verified_costs,
        )
        if coupon_intent_id:
            from apps.nuvemshop.coupon_settlement import settle_coupon_after_psp_capture
            settle_coupon_after_psp_capture(
                intent_id=coupon_intent_id, capture_evidence_id=proof_evidence.pk,
            )
        return grant, created
