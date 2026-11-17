"""Regra de acúmulo compartilhada pelo motor.

Os limites são os mesmos de ``apps.sales.quote.validate_rule`` para que a
pré-visualização, o regulamento e o motor nunca divirjam.
"""
from dataclasses import dataclass

EXPIRY_FIXED = "fixed"
EXPIRY_ROLLING = "rolling"
EXPIRY_POLICIES = (EXPIRY_FIXED, EXPIRY_ROLLING)
MAX_AMOUNT_CENTS = 100_000_000


def _is_int(value):
    return type(value) is int


@dataclass(frozen=True)
class Rule:
    points: int
    per_cents: int
    hold_days: int
    validity_days: int
    expiry_policy: str = EXPIRY_FIXED
    # Teto da renovação contado a partir da liberação (limita o passivo).
    renewal_cap_days: int | None = None

    def __post_init__(self):
        if not (_is_int(self.points) and 1 <= self.points <= 100_000
                and _is_int(self.per_cents) and 100 <= self.per_cents <= MAX_AMOUNT_CENTS
                and _is_int(self.hold_days) and 0 <= self.hold_days <= 90
                and _is_int(self.validity_days) and 1 <= self.validity_days <= 1095):
            raise ValueError("Valores fora dos limites da regra.")
        if self.expiry_policy not in EXPIRY_POLICIES:
            raise ValueError("Política de validade desconhecida.")
        if self.renewal_cap_days is not None:
            if self.expiry_policy != EXPIRY_ROLLING:
                raise ValueError("Teto de renovação só existe na validade renovável.")
            if not (_is_int(self.renewal_cap_days)
                    and self.validity_days <= self.renewal_cap_days <= 1825):
                raise ValueError("Teto de renovação inválido.")


def rule_from_mapping(data):
    """Aceita o formato de ``PointRuleDraft``/``validate_rule`` + campos novos opcionais."""
    if not isinstance(data, dict):
        raise ValueError("Regra inválida.")
    required = {"points", "per_cents", "hold_days", "validity_days"}
    optional = {"expiry_policy", "renewal_cap_days"}
    keys = set(data)
    if not required <= keys or keys - required - optional:
        raise ValueError("Campos da regra inválidos.")
    return Rule(**data)


def points_for(rule, eligible_cents):
    """Arredondamento para baixo, idêntico a ``preview_points``."""
    if not _is_int(eligible_cents) or not 0 <= eligible_cents <= MAX_AMOUNT_CENTS:
        raise ValueError("Valor elegível inválido.")
    return eligible_cents * rule.points // rule.per_cents


def minimum_spend_cents(rule, points_needed):
    """Menor valor elegível (centavos) que gera ``points_needed`` numa compra."""
    if not _is_int(points_needed) or points_needed < 0:
        raise ValueError("Pontos inválidos.")
    # ceil(points_needed * per_cents / points) em inteiros
    return -(-points_needed * rule.per_cents // rule.points)
