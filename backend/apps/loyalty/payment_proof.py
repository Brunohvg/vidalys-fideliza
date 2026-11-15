"""Fonte financeira independente: Pagar.me v5 via GET autenticado e caixa 2 operadores.

Jamais confiar em order/paid, webhook não verificado, campo POST do comprador,
CPF/PII, ou só no total informado pela plataforma. Não grava tokens.
"""
import base64
import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from apps.loyalty.models import FinancialEvidence, PaymentProofAudit
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant, TenantMembership


class PaymentProofBlocked(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


CHARGE_ID = re.compile(r"^ch_[A-Za-z0-9_-]{8,60}$")
REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{3,99}$")


def fetch_pagarme_charge(*, charge_id, secret_key, opener=None):
    """GET id fixo no Pagar.me: sem webhooks, redirects, retry ou URL livre."""
    if not isinstance(charge_id, str) or not CHARGE_ID.fullmatch(charge_id):
        raise PaymentProofBlocked("ID de cobrança inválido.")
    if not isinstance(secret_key, str) or not 16 <= len(secret_key) <= 200:
        raise PaymentProofBlocked("Chave PSP indisponível.")
    token = base64.b64encode((secret_key + ":").encode()).decode("ascii")
    req = Request(
        "https://api.pagar.me/core/v5/charges/" + charge_id,
        method="GET",
        headers={"Accept": "application/json", "Authorization": "Basic " + token},
    )
    try:
        with (opener or build_opener(_NoRedirect())).open(req, timeout=8) as response:
            if response.status != 200:
                raise PaymentProofBlocked("PSP não retornou sucesso.")
            body = response.read(131073)
            if len(body) > 131072:
                raise PaymentProofBlocked("Resposta PSP excede limite.")
            result = json.loads(body, parse_float=str)
            if not isinstance(result, dict):
                raise PaymentProofBlocked("Resposta PSP malformada.")
            return result
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, ValueError):
        raise PaymentProofBlocked("Consulta PSP indisponível.") from None


def _valid_timestamp(value):
    if not isinstance(value, str):
        raise PaymentProofBlocked("PSP não informou data de captura.")
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PaymentProofBlocked("Data de captura inválida.") from None
    if (timezone.is_naive(when) or when > timezone.now()
            or when < timezone.now() - timedelta(days=365 * 3)):
        raise PaymentProofBlocked("Data de captura fora do intervalo.")
    return when


def validate_pagarme_capture(*, charge, sale, charge_id):
    """Aceita somente charge paid/captured com pedido identificável por código.

    Um ID de cobrança escolhido livremente não é suficiente: requer vínculo
    independente entre charge.order.code e a referência imutável do SaleRecord.
    """
    if not isinstance(charge, dict) or charge.get("id") != charge_id:
        raise PaymentProofBlocked("Cobrança pertence a outra transação.")
    order = charge.get("order")
    last = charge.get("last_transaction")
    if (not isinstance(order, dict) or not isinstance(last, dict)
            or order.get("code") != sale.external_reference
            or not isinstance(order.get("id"), str)
            or not order["id"].startswith("or_")):
        raise PaymentProofBlocked("PSP não comprova vínculo com o pedido original.")
    if (charge.get("status") != "paid"
            or charge.get("currency", "BRL") != "BRL"
            or charge.get("payment_method") not in ("credit_card", "pix", "boleto")
            or last.get("status") not in ("captured", "paid")
            or last.get("success") is not True
            or charge.get("amount") != sale.reported_total_cents
            or charge.get("paid_amount") != sale.reported_total_cents
            or last.get("amount") != sale.reported_total_cents
            or type(charge.get("refunded_amount")) is not int
            or charge.get("refunded_amount") != 0
            or type(last.get("refunded_amount")) is not int
            or last.get("refunded_amount") != 0):
        raise PaymentProofBlocked("Captura total e irreversões não comprovadas.")
    paid_at = _valid_timestamp(charge.get("paid_at"))
    # Importação do pedido pode ocorrer depois da captura remota;
    # comparação com consent_at é feita pelo motor de grants.
    return paid_at


def _digest(*, tenant_id, sale_id, provider, external_id, amount, occurred_at):
    canonical = json.dumps(
        [str(tenant_id), str(sale_id), provider, external_id,
         amount, occurred_at.isoformat()],
        separators=(",", ":"), ensure_ascii=True,
    )
    return salted_hmac(
        "vidalys.payment-proof.v1", canonical, secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


def _record_proof(*, sale, provider, external_id, captured_at,
                  operator=None, reviewer=None):
    """Append-only: uma cobrança não comprova duas compras/duas lojas."""
    if not REFERENCE.fullmatch(external_id):
        raise PaymentProofBlocked("Referência externa não autorizada.")
    if sale.order_status != SaleRecord.OrderStatus.PAID or sale.reported_total_cents <= 0:
        raise PaymentProofBlocked("Venda não consta paga/recebida para conciliação.")
    ref = provider + ":" + external_id
    existing = PaymentProofAudit.objects.select_related("evidence").filter(
        provider_reference=ref,
    ).first()
    if existing:
        if (existing.sale_id != sale.pk or existing.tenant_id != sale.tenant_id
                or existing.evidence.amount_cents != sale.reported_total_cents):
            raise PaymentProofBlocked("Comprovação vinculada a outro pedido/valor.")
        return existing.evidence, False
    digest = _digest(
        tenant_id=sale.tenant_id, sale_id=sale.pk, provider=provider,
        external_id=external_id, amount=sale.reported_total_cents,
        occurred_at=captured_at,
    )
    evidence = FinancialEvidence.objects.create(
        tenant=sale.tenant, sale=sale,
        kind=FinancialEvidence.Kind.CAPTURE, provider=provider,
        external_event_id=external_id,
        amount_cents=sale.reported_total_cents,
        verification_digest=digest,
        occurred_at=captured_at, verified_at=timezone.now(),
    )
    PaymentProofAudit.objects.create(
        tenant=sale.tenant, sale=sale, evidence=evidence,
        provider=provider, provider_reference=ref,
        proof_digest=digest, operator=operator, reviewer=reviewer,
        verified_at=timezone.now(),
    )
    return evidence, True


@transaction.atomic
def record_pagarme_capture(*, sale_id, charge_id, remote, secret_verified=False):
    """Somente adaptador interno que FEZ GET com credencial do tenant pode chamar.

    Não exposto em View nem aceita payload JSON do cliente.
    """
    if not (getattr(settings, "FIDELIZA_PAYMENT_PROOF_ENABLED", False)
            and "pagarme_v5" in settings.FIDELIZA_TRUSTED_PAYMENT_ADAPTERS
            and secret_verified):
        raise PaymentProofBlocked("Adaptador PSP não liberado.")
    sale = SaleRecord.objects.select_related("tenant").select_for_update().get(pk=sale_id)
    Tenant.objects.select_for_update().get(pk=sale.tenant_id)
    if not sale.tenant.loyalty_live_enabled:
        raise PaymentProofBlocked("Loja sem ativação explícita.")
    captured_at = validate_pagarme_capture(
        charge=remote, sale=sale, charge_id=charge_id,
    )
    return _record_proof(
        sale=sale, provider="pagarme_v5", external_id=charge_id,
        captured_at=captured_at,
    )


def verify_and_record_pagarme_capture(*, sale_id, charge_id, opener=None):
    """Única entrada operacional PSP: chave de QA guardada no secret manager.

    A conta Pagar.me desta chave só pode ser usada por tenant explicitamente
    PINADO, prevenindo cobrança de outro lojista com credenciais globais.
    """
    key = os.environ.get("FIDELIZA_PAGARME_QA_SECRET", "")
    pin = os.environ.get("FIDELIZA_PAGARME_QA_TENANT_ID", "")
    sale = SaleRecord.objects.select_related("tenant").get(pk=sale_id)
    if (not pin or str(sale.tenant_id) != pin
            or not re.fullmatch(r"(qa|homolog)-[a-z0-9-]{3,52}", sale.tenant.slug)):
        raise PaymentProofBlocked("Credencial PSP QA não corresponde à loja.")
    remote = fetch_pagarme_charge(
        charge_id=charge_id, secret_key=key, opener=opener,
    )
    return record_pagarme_capture(
        sale_id=sale.pk, charge_id=charge_id,
        remote=remote, secret_verified=True,
    )


@transaction.atomic
def record_cash_dual_control(*, sale_id, receipt_reference, operator_id,
                             reviewer_id, received_at, counted_cents):
    """Fechamento presencial com duas pessoas autenticadas da MESMA loja.

    Um relatório de PDV sem dupla conferência não é evidência de caixa.
    Não é PSP nem prova de depósito bancário; aplica-se somente ao balcão.
    """
    if not (getattr(settings, "FIDELIZA_CASH_DUAL_CONTROL_ENABLED", False)
            and "cash_dual_control" in settings.FIDELIZA_TRUSTED_PAYMENT_ADAPTERS):
        raise PaymentProofBlocked("Fechamento de caixa ainda desativado.")
    sale = SaleRecord.objects.select_related("tenant").select_for_update().get(pk=sale_id)
    Tenant.objects.select_for_update().get(pk=sale.tenant_id)
    if (sale.channel != SaleRecord.Channel.COUNTER
            or not sale.tenant.loyalty_live_enabled
            or type(counted_cents) is not int
            or counted_cents != sale.reported_total_cents
            or not isinstance(receipt_reference, str)
            or not REFERENCE.fullmatch(receipt_reference)
            or operator_id == reviewer_id):
        raise PaymentProofBlocked("Fechamento, valor ou dupla conferência inválidos.")
    if (timezone.is_naive(received_at) or received_at > timezone.now()
            or received_at < sale.created_at - timedelta(minutes=5)):
        raise PaymentProofBlocked("Horário de caixa inválido.")
    members = TenantMembership.objects.filter(
        tenant=sale.tenant, user_id__in=[operator_id, reviewer_id],
        role__in=[TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN],
        user__is_active=True,
    ).values_list("user_id", flat=True)
    if len(set(members)) != 2:
        raise PaymentProofBlocked("Dois responsáveis diferentes e autenticados são obrigatórios.")
    if sale.submitted_by_id is not None and sale.submitted_by_id != operator_id:
        raise PaymentProofBlocked("Operador de recebimento diverge da venda lançada.")
    return _record_proof(
        sale=sale, provider="cash_dual_control", external_id=receipt_reference,
        captured_at=received_at,
        operator=next(m.user for m in TenantMembership.objects.select_related("user").filter(
            tenant=sale.tenant, user_id=operator_id)),
        reviewer=next(m.user for m in TenantMembership.objects.select_related("user").filter(
            tenant=sale.tenant, user_id=reviewer_id)),
    )


def credit_verified_sale(*, evidence_id, costs):
    """Crédito em pontos/cashback somente via motor de margem existente.

    O motor aplica hold_days, limite de orçamento, saldo por grant e idempotência.
    """
    from .services import grant_for_captured_sale
    proof = PaymentProofAudit.objects.select_related("evidence").get(
        evidence_id=evidence_id,
    )
    if proof.evidence.kind != FinancialEvidence.Kind.CAPTURE:
        raise PaymentProofBlocked("Sem captura verificada.")
    return grant_for_captured_sale(
        sale_id=proof.sale_id, evidence_id=proof.evidence_id, costs=costs,
    )
