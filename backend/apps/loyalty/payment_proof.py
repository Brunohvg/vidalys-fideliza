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

from apps.loyalty.models import CashClosing, FinancialEvidence, VerifiedPaymentProof
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant, TenantMembership
from apps.nuvemshop.pagarme_payment import fetch_charge, validate_paid_charge, PaymentProviderError

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


@transaction.atomic
def apply_verified_capture(*, evidence_id, costs, coupon_intent_id=None):
    """Only source-backed proof may enter monetary loyalty domain.

    Uses existing SKU-cost, margin and budget gate, never bypasses it.
    """
    if not (settings.FIDELIZA_POINTS_WRITES_ENABLED
            and settings.FIDELIZA_LEDGER_WRITES_ENABLED
            and settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED):
        raise PaymentProofBlocked("Ledger financeiro desligado")
    proof = VerifiedPaymentProof.objects.select_related("evidence__sale").get(
        evidence_id=evidence_id,
    )
    evidence = proof.evidence
    if evidence.provider not in settings.FIDELIZA_TRUSTED_PAYMENT_ADAPTERS:
        raise PaymentProofBlocked("Provedor não aprovado para execução")
    tenant = Tenant.objects.select_for_update().get(pk=proof.tenant_id)
    _gate(tenant)
    if evidence.tenant_id != tenant.pk or evidence.sale.tenant_id != tenant.pk:
        raise PaymentProofBlocked("Prova não pertence ao tenant")
    from apps.loyalty.services import grant_for_captured_sale
    grant, created = grant_for_captured_sale(
        sale_id=evidence.sale_id, evidence_id=evidence.pk, costs=costs,
    )
    if coupon_intent_id:
        from apps.nuvemshop.coupon_settlement import settle_coupon_after_psp_capture
        settled, _ = settle_coupon_after_psp_capture(
            intent_id=coupon_intent_id, capture_evidence_id=evidence.pk,
        )
    return grant, created
