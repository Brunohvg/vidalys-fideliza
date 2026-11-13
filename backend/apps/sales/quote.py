"""Simulação determinística de pontos. Valores monetários apenas em centavos."""
MAX_AMOUNT_CENTS = 100_000_000  # até R$ 1 milhão
MAX_QUOTED_POINTS = 100_000_000


def is_int(value):
    return type(value) is int


def validate_rule(payload):
    expected = {"points", "per_cents", "hold_days", "validity_days"}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError("A regra deve conter pontos, base, carência e validade.")
    points = payload["points"]
    per_cents = payload["per_cents"]
    hold = payload["hold_days"]
    validity = payload["validity_days"]
    if not (is_int(points) and 1 <= points <= 100000
            and is_int(per_cents) and 100 <= per_cents <= MAX_AMOUNT_CENTS
            and is_int(hold) and 0 <= hold <= 90
            and is_int(validity) and 1 <= validity <= 1095):
        raise ValueError("Valores fora dos limites da regra.")
    return payload


def preview_points(*, eligible_amount_cents, points, per_cents):
    if (not is_int(eligible_amount_cents) or
            not 0 <= eligible_amount_cents <= MAX_AMOUNT_CENTS):
        raise ValueError("Valor elegível inválido.")
    if not (is_int(points) and is_int(per_cents) and points > 0 and per_cents > 0):
        raise ValueError("Regra inválida.")
    value = eligible_amount_cents * points // per_cents
    if value > MAX_QUOTED_POINTS:
        raise ValueError("Simulação excede o limite de segurança.")
    return value
