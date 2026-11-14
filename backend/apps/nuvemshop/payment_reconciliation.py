"""G7: conciliação determinística de fatos financeiros NORMALIZADOS, sem IO.

IMPORTANTE: estes fatos não possuem cadeia de confiança até que um adaptador
PSP/ERP autenticado seja implementado. Igualdade matemática NÃO libera crédito.
Nunca chamar isto com payload HTTP direto, webhook de loja ou dados pessoais.
"""
from dataclasses import dataclass
import re

MAX_EVENTS = 200
MAX_CENTS = 100_000_000_000
SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
SAFE_PROVIDER = re.compile(r"^[a-z0-9_.-]{2,50}$")
KINDS = frozenset({"capture", "refund", "chargeback"})


class PaymentReconciliationError(ValueError):
    """Fatos inválidos ou contraditórios exigem revisão, nunca concessão."""


@dataclass(frozen=True)
class PaymentFact:
    tenant_id: str
    store_id: str
    order_id: str
    provider: str
    event_id: str
    transaction_id: str
    kind: str
    amount_cents: int
    currency: str = "BRL"
    original_capture_id: str = ""

    def validate(self):
        for name in ("tenant_id", "store_id", "order_id", "event_id", "transaction_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not SAFE_REFERENCE.fullmatch(value):
                raise PaymentReconciliationError("Identificador financeiro inválido")
        if not isinstance(self.provider, str) or not SAFE_PROVIDER.fullmatch(self.provider):
            raise PaymentReconciliationError("Provedor inválido")
        if (not isinstance(self.kind, str) or self.kind not in KINDS
                or not isinstance(self.currency, str) or self.currency != "BRL"):
            raise PaymentReconciliationError("Tipo ou moeda inválida")
        if (type(self.amount_cents) is not int or
                not 0 < self.amount_cents <= MAX_CENTS):
            raise PaymentReconciliationError("Montante inválido")
        if self.kind == "capture":
            if self.original_capture_id:
                raise PaymentReconciliationError("Captura não referencia outra captura")
        elif (not isinstance(self.original_capture_id, str)
              or not SAFE_REFERENCE.fullmatch(self.original_capture_id)):
            raise PaymentReconciliationError("Reversão sem captura de origem")


def reconcile_payment_facts(snapshot, facts, *, tenant_id, store_id):
    """Retorna somente diagnóstico; nunca qualifica cashback ou comprova PSP.

    snapshot: resultado existente de summarize_order(), sem dados pessoais.
    facts: Iterable[PaymentFact] de um futuro adaptador de confiança.
    A origem desses dados NAO é autenticada por esta função.
    """
    if not isinstance(snapshot, dict) or snapshot.get("source") != "nuvemshop_live_read_only":
        raise PaymentReconciliationError("Prévia oficial do pedido obrigatória")
    order_id = snapshot.get("order_id")
    total = snapshot.get("reported_total_cents")
    if (not isinstance(order_id, str) or not SAFE_REFERENCE.fullmatch(order_id)
            or not isinstance(tenant_id, str) or not SAFE_REFERENCE.fullmatch(tenant_id)
            or not isinstance(store_id, str) or not SAFE_REFERENCE.fullmatch(store_id)
            or type(total) is not int or not 0 <= total <= MAX_CENTS
            or snapshot.get("currency") != "BRL"):
        raise PaymentReconciliationError("Escopo ou moeda do pedido inválidos")
    if not isinstance(facts, (list, tuple)) or len(facts) > MAX_EVENTS:
        raise PaymentReconciliationError("Quantidade de transações inválida")

    unique_events = {}
    captures = {}
    unique_operations = set()
    for fact in facts:
        if not isinstance(fact, PaymentFact):
            raise PaymentReconciliationError("Evidência financeira não normalizada")
        fact.validate()
        if (fact.tenant_id != tenant_id or fact.store_id != store_id
                or fact.order_id != order_id or fact.currency != snapshot["currency"]):
            raise PaymentReconciliationError("Transação de outra loja/pedido/moeda")
        event_key = (fact.provider, fact.event_id)
        existing = unique_events.get(event_key)
        if existing:
            if existing != fact:
                raise PaymentReconciliationError("Evento repetido com conteúdo diferente")
            continue
        unique_events[event_key] = fact
        operation_key = (fact.provider, fact.kind, fact.transaction_id)
        if operation_key in unique_operations:
            # Alguns gateways emitem IDs de evento diferentes para a mesma
            # operação; sem contrato específico isso exige revisão.
            raise PaymentReconciliationError("Operação financeira duplicada")
        unique_operations.add(operation_key)
        if fact.kind == "capture":
            capture_key = (fact.provider, fact.transaction_id)
            if capture_key in captures:
                raise PaymentReconciliationError("Captura duplicada da mesma transação")
            captures[capture_key] = fact.amount_cents

    refunded = 0
    charged_back = 0
    reversal_by_capture = {}
    for fact in unique_events.values():
        if fact.kind in ("refund", "chargeback"):
            capture_key = (fact.provider, fact.original_capture_id)
            if capture_key not in captures:
                raise PaymentReconciliationError("Reversão sem captura correspondente")
            reversal_by_capture[capture_key] = (
                reversal_by_capture.get(capture_key, 0) + fact.amount_cents
            )
            if reversal_by_capture[capture_key] > captures[capture_key]:
                raise PaymentReconciliationError("Reversões excedem captura de origem")
            if fact.kind == "refund":
                refunded += fact.amount_cents
            else:
                charged_back += fact.amount_cents

    captured = sum(captures.values())
    total_reversals = refunded + charged_back
    if total_reversals > captured or captured > MAX_CENTS:
        raise PaymentReconciliationError("Estorno maior que capturas ou limite excedido")

    reported_paid = snapshot.get("reported_customer_paid_cents")
    if reported_paid is not None and (
        type(reported_paid) is not int or not 0 <= reported_paid <= MAX_CENTS
    ):
        raise PaymentReconciliationError("Valor reportado inválido")

    status = snapshot.get("review_status")
    if snapshot.get("order_status") == "cancelled" or status in (
        "blocked_cancelled", "blocked_refund", "blocked_chargeback",
    ):
        result = "order_cancelled_or_refunded"
    elif charged_back:
        result = "chargeback_review"
    elif refunded:
        result = "refund_review"
    elif not captured:
        result = "no_independent_payment_facts"
    elif snapshot.get("payment_status") != "paid":
        result = "platform_payment_not_paid"
    elif status == "manual_payment_review":
        result = "manual_payment_review"
    elif captured != total:
        result = "capture_total_mismatch"
    elif reported_paid is None:
        result = "platform_paid_amount_missing"
    elif reported_paid != captured:
        result = "platform_paid_amount_mismatch"
    elif not snapshot.get("participant_verified"):
        result = "participant_not_verified"
    else:
        result = "amounts_match_but_provider_not_authenticated"

    return {
        "mode": "offline_reconciliation_only",
        "order_id": order_id,
        "currency": "BRL",
        "review_status": result,
        "captured_cents": captured,
        "refunded_cents": refunded,
        "chargeback_cents": charged_back,
        "net_cents": captured - total_reversals,
        "reported_total_cents": total,
        "reported_customer_paid_cents": reported_paid,
        "unique_financial_events": len(unique_events),
        "duplicate_deliveries_ignored": len(facts) - len(unique_events),
        "independent_psp_proof_verified": False,
        "payment_eligible_for_rewards": False,
        "credit_eligible": False,
        "cashback_created": False,
        "ledger_writes_performed": 0,
        "requires_authenticated_provider_adapter": True,
        "requires_refund_chargeback_policy": True,
        "requires_margin_and_campaign_budget_validation": True,
    }
