"""Núcleo puro do futuro motor de benefícios, inicialmente só simulação.

Nenhuma função usa Django ORM, carteira, PII, pagamentos ou APIs externas.
Campos de cenário são hipóteses do usuário, jamais fatos verificados.
"""
from dataclasses import dataclass


GOALS = frozenset(("second_purchase", "reactivation", "recurrence"))
REACTIVATION_DAYS = 60


def _integer(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name}: valor inválido")
    return value


def estimate_cashback_cents(amount_cents: int, rate_bps: int) -> int:
    """Arredondamento determinístico para centavos, sem float."""
    _integer("amount_cents", amount_cents, 0, 1_000_000_000)
    _integer("rate_bps", rate_bps, 1, 1000)
    return (amount_cents * rate_bps + 5000) // 10000


def exposure_summary(ticket_cents, rate_bps, projected_paid_orders, budget_cents):
    _integer("projected_paid_orders", projected_paid_orders, 1, 50_000)
    _integer("budget_cents", budget_cents, 1, 1_000_000_000)
    credit = estimate_cashback_cents(ticket_cents, rate_bps)
    exposure = credit * projected_paid_orders
    return {
        "credit_per_order_cents": credit,
        "max_exposure_cents": exposure,
        "exceeds_budget": exposure > budget_cents,
        "assumptions_only": True,
    }


@dataclass(frozen=True)
class BenefitRule:
    """Projeção de um CampaignDraft já existente, sem uma segunda configuração."""
    goal: str
    rate_bps: int
    ticket_cents: int
    projected_paid_orders: int
    budget_cents: int
    version: int

    def validate(self):
        if self.goal not in GOALS:
            raise ValueError("Objetivo não suportado")
        _integer("ticket_cents", self.ticket_cents, 1, 1_000_000_000)
        _integer("rate_bps", self.rate_bps, 1, 1000)
        _integer("projected_paid_orders", self.projected_paid_orders, 1, 50_000)
        _integer("budget_cents", self.budget_cents, 1, 1_000_000_000)
        _integer("version", self.version, 1, 2_147_483_647)


@dataclass(frozen=True)
class HypotheticalPurchase:
    order_amount_cents: int
    prior_paid_orders: int
    days_since_last_paid_order: int | None = None
    committed_budget_cents: int = 0

    def validate(self):
        _integer("order_amount_cents", self.order_amount_cents, 1, 1_000_000_000)
        _integer("prior_paid_orders", self.prior_paid_orders, 0, 50_000)
        if self.days_since_last_paid_order is not None:
            _integer("days_since_last_paid_order", self.days_since_last_paid_order, 0, 36500)
        _integer("committed_budget_cents", self.committed_budget_cents, 0, 1_000_000_000)
        if self.prior_paid_orders == 0 and self.days_since_last_paid_order is not None:
            raise ValueError("Não existe última compra quando histórico é zero")


def _goal_result(rule, scenario):
    if rule.goal == "second_purchase":
        return (scenario.prior_paid_orders == 1,
                "second_purchase_requires_exactly_one_prior_order")
    if rule.goal == "reactivation":
        if scenario.prior_paid_orders < 1:
            return False, "reactivation_requires_prior_order"
        if scenario.days_since_last_paid_order is None:
            return False, "reactivation_requires_inactivity_days"
        return (
            scenario.days_since_last_paid_order >= REACTIVATION_DAYS,
            "reactivation_requires_60_days",
        )
    if rule.goal == "recurrence":
        return (
            scenario.prior_paid_orders >= 2,
            "recurrence_requires_at_least_two_prior_orders",
        )
    raise ValueError("Objetivo não suportado")


def simulate_benefit(rule: BenefitRule, scenario: HypotheticalPurchase) -> dict:
    """Avalia uma hipótese sem afirmar que houve compra ou autorizar crédito."""
    rule.validate()
    scenario.validate()
    forecast = exposure_summary(
        rule.ticket_cents, rule.rate_bps,
        rule.projected_paid_orders, rule.budget_cents,
    )
    matches, reason = _goal_result(rule, scenario)
    potential = estimate_cashback_cents(
        scenario.order_amount_cents, rule.rate_bps,
    )
    remaining = max(rule.budget_cents - scenario.committed_budget_cents, 0)
    if not matches:
        state = "goal_not_met"
        projected_reward = 0
    elif potential == 0:
        state = "reward_below_one_cent"
        projected_reward = 0
    elif potential > remaining:
        state = "budget_insufficient"
        projected_reward = 0
    else:
        state = "hypothetical_match"
        projected_reward = potential

    return {
        "mode": "simulation_only",
        "benefit_type": "cashback",
        "goal": rule.goal,
        "rule_version": rule.version,
        "state": state,
        "goal_failure_code": None if matches else reason,
        "hypothetical_goal_met": matches,
        "estimated_reward_cents": projected_reward,
        "uncapped_reward_cents": potential,
        "remaining_budget_cents": remaining,
        "forecast": forecast,
        "activation_available": False,
        "requires_verified_purchase_and_identity": True,
        "requires_independent_payment_reconciliation": True,
        "credit_eligible": False,
        "ledger_writes_performed": 0,
    }
