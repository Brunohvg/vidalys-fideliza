"""Planejamento conservador de campanha, sem persistência nem concessão de benefícios.

Cálculos usam centavos e pontos-base inteiros. Os pedidos projetados são
hipóteses digitadas pelo lojista, NÃO previsões baseadas na Nuvemshop.
"""
from .services import _max_safe_rate, simulate_margin


def plan_campaign(data: dict) -> dict:
    per_order = simulate_margin(data)
    orders = data["projected_paid_orders"]
    budget = data["campaign_budget_cents"]
    committed = data["already_committed_cents"]

    planned_per_order = per_order["estimated_cashback_exposure_cents"]
    future_exposure = planned_per_order * orders
    total_exposure = committed + future_exposure
    available = max(0, budget - committed)
    exceeded_before_start = committed > budget
    budget_ok = not exceeded_before_start and future_exposure <= available

    max_orders = None if planned_per_order == 0 else available // planned_per_order
    rate_from_budget = _max_safe_rate(
        per_order["eligible_net_revenue_cents"], available // orders
    )

    margin_status = per_order["status"]
    if margin_status == "cost_unknown":
        status = "cost_unknown"
    elif margin_status == "margin_already_below_target":
        status = "margin_already_below_target"
    elif exceeded_before_start:
        status = "budget_already_exceeded"
    elif margin_status == "cashback_exceeds_margin":
        status = "cashback_exceeds_margin"
    elif not budget_ok:
        status = "campaign_budget_exceeded"
    else:
        status = "within_limits"

    can_suggest = (
        not exceeded_before_start
        and margin_status not in ("cost_unknown", "margin_already_below_target")
    )
    recommended_rate = (
        min(per_order["maximum_safe_cashback_bps"], rate_from_budget)
        if can_suggest else None
    )
    # Calculadora não aprova crédito ou campanha, mesmo se status for positivo.
    return {
        "mode": "planning_only",
        "currency": "BRL",
        "status": status,
        "automatically_approved": False,
        "projected_paid_orders": orders,
        "cashback_rate_bps": data["proposed_cashback_bps"],
        "per_order_net_revenue_cents": per_order["eligible_net_revenue_cents"],
        "per_order_cashback_cents": planned_per_order,
        "campaign_budget_cents": budget,
        "already_committed_cents": committed,
        "available_campaign_budget_cents": available,
        "projected_new_exposure_cents": future_exposure,
        "projected_total_exposure_cents": total_exposure,
        "estimated_order_capacity": max_orders,
        "budget_within_limit": budget_ok,
        "margin_within_target": margin_status == "within_target",
        "maximum_margin_rate_bps": per_order["maximum_safe_cashback_bps"],
        "maximum_budget_rate_bps": rate_from_budget,
        "suggested_limit_rate_bps": recommended_rate,
        "per_order_contribution_after_cents": per_order["contribution_after_cents"],
        "projected_contribution_after_cents": (
            per_order["contribution_after_cents"] * orders
            if per_order["contribution_after_cents"] is not None else None
        ),
        "warnings": [
            "Pedidos projetados são hipóteses, não pedidos pagos ou previsão de demanda.",
            "O crédito é uma exposição potencial integral, não saldo realmente resgatado.",
            "Custos, impostos ou descontos não informados não estão no cálculo.",
            "A simulação não reserva orçamento nem ativa campanhas.",
        ],
    }
