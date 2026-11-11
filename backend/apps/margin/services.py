"""Simulador conservador de margem. Sem mutações em pedidos ou carteiras.

Valores monetários são centavos e taxas são pontos-base (100 bps = 1%).
O custo do cashback é tratado como exposição POTENCIAL integral, sem presumir
que o cliente resgatará ou que a recompensa seja contabilizada como despesa imediata.
"""


def _round_basis_points(amount_cents: int, bps: int) -> int:
    # Inteiros não negativos: arredondamento half-up em centavos.
    return (amount_cents * bps + 5000) // 10000


def _ceil_basis_points(amount_cents: int, bps: int) -> int:
    return (amount_cents * bps + 9999) // 10000


def _max_safe_rate(net_cents: int, reward_budget_cents: int) -> int:
    """Máxima taxa inteira em bps que respeita o orçamento após arredondamento."""
    lo, hi = 0, 10000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _round_basis_points(net_cents, mid) <= reward_budget_cents:
            lo = mid
        else:
            hi = mid - 1
    return lo


def simulate_margin(data: dict) -> dict:
    """Executa apenas cálculos hipotéticos; jamais aprova campanha automaticamente."""
    gross = data["eligible_subtotal_cents"]
    discounts = data["existing_discounts_cents"]
    net = gross - discounts
    requested_bps = data["proposed_cashback_bps"]
    required_bps = data["minimum_margin_bps"]
    exposure = _round_basis_points(net, requested_bps)
    known_costs = (
        data["payment_fee_cents"]
        + data["shipping_subsidy_cents"]
        + data["other_variable_costs_cents"]
    )
    base = {
        "mode": "simulation_only",
        "currency": "BRL",
        "eligible_net_revenue_cents": net,
        "estimated_cashback_exposure_cents": exposure,
        "proposed_cashback_bps": requested_bps,
        "minimum_margin_bps": required_bps,
        "automatically_approved": False,
        "contribution_before_cents": None,
        "contribution_after_cents": None,
        "margin_after_bps": None,
        "safe_cashback_budget_cents": None,
        "maximum_safe_cashback_bps": None,
    }

    cogs = data["cost_of_goods_cents"]
    if cogs is None:
        return {
            **base,
            "status": "cost_unknown",
            "warnings": [
                "Custo da mercadoria ausente. Não é possível validar a margem.",
                "O crédito é uma exposição potencial, não cashback concedido ou resgatado.",
            ],
        }

    before = net - cogs - known_costs
    after = before - exposure
    floor = _ceil_basis_points(net, required_bps)
    safe_budget = min(net, max(0, before - floor))
    safe_bps = _max_safe_rate(net, safe_budget)

    if before < floor:
        status = "margin_already_below_target"
        warnings = ["A margem já está abaixo do mínimo antes da recompensa."]
    elif exposure > safe_budget:
        status = "cashback_exceeds_margin"
        warnings = ["Cashback proposto ultrapassa a margem mínima configurada."]
    else:
        status = "within_target"
        warnings = ["Simulação dentro do limite informado, sem aprovação automática."]

    return {
        **base,
        "status": status,
        "contribution_before_cents": before,
        "contribution_after_cents": after,
        "margin_after_bps": (after * 10000) // net,
        "safe_cashback_budget_cents": safe_budget,
        "maximum_safe_cashback_bps": safe_bps,
        "warnings": warnings + [
            "Não inclui impostos, tarifas ou custos que não tenham sido informados.",
            "A exposição representa o crédito integral potencial, não o resgate efetivo.",
        ],
    }
