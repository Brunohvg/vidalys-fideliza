"""Meta com Margem: a próxima recompensa do cliente, escolhida pelo custo.

Dor medida: 58,4% aderem para chegar a um objetivo maior (Panorama 2026);
do lado do lojista, fidelidade costuma ser vista como custo que corrói margem.

A meta sugerida fica entre as recompensas mais próximas do saldo (até 3, custando
no máximo 1,5x a mais próxima — efeito de proximidade do objetivo) e, dentro dessa janela, prefere a de maior
**valor percebido por real de custo** (ex.: brinde de R$ 40 que custa R$ 12).
Custo desconhecido nunca vira zero: a recompensa só entra no ranking de margem
quando o custo foi informado.
"""
from dataclasses import dataclass
from fractions import Fraction

from .rules import minimum_spend_cents

NEAREST_WINDOW = 3
# Só disputa a meta quem custa até 1,5x a recompensa mais próxima (efeito de proximidade).
NEAREST_STRETCH = Fraction(3, 2)


@dataclass(frozen=True)
class Reward:
    id: str
    title: str
    points_cost: int
    perceived_value_cents: int
    merchant_cost_cents: int | None
    active: bool = True
    stock: int | None = None  # None = sem limite de estoque

    def __post_init__(self):
        if type(self.points_cost) is not int or self.points_cost <= 0:
            raise ValueError("Custo em pontos inválido.")
        if type(self.perceived_value_cents) is not int or self.perceived_value_cents <= 0:
            raise ValueError("Valor percebido inválido.")
        if self.merchant_cost_cents is not None and (
                type(self.merchant_cost_cents) is not int or self.merchant_cost_cents < 0):
            raise ValueError("Custo do lojista inválido.")
        if self.stock is not None and (type(self.stock) is not int or self.stock < 0):
            raise ValueError("Estoque inválido.")

    @property
    def available(self):
        return self.active and self.stock != 0


def value_ratio(reward):
    """Valor percebido ÷ custo real. ``None`` quando o custo é desconhecido ou zero."""
    if not reward.merchant_cost_cents:
        return None
    return Fraction(reward.perceived_value_cents, reward.merchant_cost_cents)


def margin_ranking(rewards):
    """Recompensas disponíveis por eficiência de custo, mais exclusões com motivo."""
    ranked, excluded = [], []
    for reward in rewards:
        if not reward.available:
            excluded.append((reward, "indisponivel"))
        elif reward.merchant_cost_cents is None:
            excluded.append((reward, "custo_desconhecido"))
        elif reward.merchant_cost_cents == 0:
            excluded.append((reward, "custo_zero_revisar"))
        else:
            ranked.append(reward)
    ranked.sort(key=lambda r: (-value_ratio(r), r.points_cost, r.id))
    return ranked, excluded


@dataclass(frozen=True)
class Goal:
    reward: Reward
    missing_points: int
    missing_spend_cents: int
    progress_percent: int
    margin_known: bool
    redeemable_now: tuple


def next_goal(balance, rewards, rule):
    """Meta sugerida ao cliente; ``None`` quando não há recompensa disponível."""
    if type(balance) is not int or balance < 0:
        raise ValueError("Saldo inválido.")
    available = [r for r in rewards if r.available]
    if not available:
        return None
    redeemable = tuple(sorted((r.id for r in available if r.points_cost <= balance)))
    ahead = sorted((r for r in available if r.points_cost > balance),
                   key=lambda r: (r.points_cost, r.id))
    if not ahead:
        # Já pode trocar tudo: a meta é a melhor troca disponível agora.
        ranked, _ = margin_ranking(available)
        best = ranked[0] if ranked else max(available, key=lambda r: (r.points_cost, r.id))
        return Goal(best, 0, 0, 100, bool(ranked), redeemable)
    limit = ahead[0].points_cost * NEAREST_STRETCH
    window = [r for r in ahead[:NEAREST_WINDOW] if r.points_cost <= limit]
    known = [r for r in window if value_ratio(r) is not None]
    if known:
        target = max(known, key=lambda r: (value_ratio(r), -r.points_cost))
    else:
        target = window[0]
    missing = target.points_cost - balance
    return Goal(
        reward=target,
        missing_points=missing,
        missing_spend_cents=minimum_spend_cents(rule, missing),
        progress_percent=min(99, balance * 100 // target.points_cost),
        margin_known=bool(known),
        redeemable_now=redeemable,
    )


def goal_message(goal):
    from . import formatting as fmt
    if goal.missing_points == 0:
        return f"Você já pode trocar seus pontos por {goal.reward.title}."
    return (f"Faltam {fmt.points(goal.missing_points)} para {goal.reward.title} — "
            f"cerca de {fmt.brl(goal.missing_spend_cents)} em compras.")
