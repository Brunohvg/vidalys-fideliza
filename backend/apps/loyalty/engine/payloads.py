"""Contrato JSON entre o motor e as telas (clube e painel).

As views Django só precisam carregar dados do banco e chamar estas funções.
O formato é o mesmo dos fixtures usados pelo frontend
(``frontend/src/club-differentials/fixtures``), gerados a partir daqui.
"""
from datetime import timedelta

from . import clarity, expiry, goals
from .club_health import lift, liability, rate

REASON_LABELS = {
    "custo_desconhecido": "Informe o custo para entrar no ranking de margem.",
    "indisponivel": "Inativa ou sem estoque.",
    "custo_zero_revisar": "Custo zero declarado: confirme se está correto.",
}


def _goal_dict(goal):
    if goal is None:
        return None
    return {
        "reward_id": goal.reward.id,
        "title": goal.reward.title,
        "points_cost": goal.reward.points_cost,
        "missing_points": goal.missing_points,
        "missing_spend_cents": goal.missing_spend_cents,
        "progress_percent": goal.progress_percent,
        "message": goals.goal_message(goal),
        "redeemable_now": list(goal.redeemable_now),
    }


def club_payload(*, store_name, club_url, rule, ledger_active, rewards, now,
                 balance=None, lots=(), milestones=(),
                 notice_offsets=clarity.DEFAULT_NOTICE_OFFSETS):
    """Payload do clube do participante.

    Com o ledger desligado, saldo/meta/vencimento são ``None`` e as recompensas
    ficam ``em_preparacao``: a tela não pode inventar números.
    """
    available = (balance or {}).get("available", 0) if ledger_active else None
    if ledger_active and (type(available) is not int or available < 0):
        raise ValueError("Saldo disponível inválido.")
    expiring = None
    if ledger_active:
        soon = [lot for lot in lots
                if lot.points > 0 and now < lot.expires_at <= now + timedelta(days=30)]
        if soon:
            first = min(lot.expires_at for lot in soon)
            expiring = {
                "points": sum(lot.points for lot in soon),
                "earliest_expiry": first.isoformat(),
                "days_left": expiry.days_left(first, now),
            }
    reward_rows = []
    for reward in sorted(rewards, key=lambda r: (not r.available, r.points_cost, r.id)):
        if not reward.available:
            state, missing = "indisponivel", None
        elif not ledger_active:
            state, missing = "em_preparacao", None
        elif reward.points_cost <= available:
            state, missing = "resgatavel", 0
        else:
            state, missing = "faltam", reward.points_cost - available
        reward_rows.append({
            "id": reward.id, "title": reward.title, "points_cost": reward.points_cost,
            "perceived_value_cents": reward.perceived_value_cents,
            "state": state, "missing_points": missing,
        })
    return {
        "ledger_active": bool(ledger_active),
        "store": {"name": store_name, "club_url": club_url},
        "rule": clarity.describe(rule, notice_offsets=notice_offsets),
        "balance": ({"available": available,
                     "pending": int((balance or {}).get("pending", 0))}
                    if ledger_active else None),
        "expiring": expiring,
        "goal": _goal_dict(goals.next_goal(available, rewards, rule)) if ledger_active else None,
        "rewards": reward_rows,
        "milestones": [{"key": m.key, "title": m.title, "message": m.message}
                       for m in milestones],
    }


def _rate_dict(result):
    return None if result is None else dict(result.__dict__)


def merchant_payload(*, rule, terms_text, rewards, now, lots=(),
                     points_outstanding=None, repurchase=None, lift_counts=None,
                     notice_offsets=clarity.DEFAULT_NOTICE_OFFSETS):
    """Payload do painel: clareza, ranking de margem e saúde do clube."""
    report = clarity.checklist(rule, terms_text=terms_text, rewards=rewards,
                               notice_offsets=notice_offsets)
    ranked, excluded = goals.margin_ranking(rewards)
    li = None if points_outstanding is None else liability(points_outstanding, rewards)
    return {
        "clarity": {**report.as_dict(),
                    "summary": clarity.describe(rule, notice_offsets=notice_offsets)},
        "margin": {
            "ranked": [{
                "id": r.id, "title": r.title, "points_cost": r.points_cost,
                "perceived_value_cents": r.perceived_value_cents,
                "merchant_cost_cents": r.merchant_cost_cents,
                "value_ratio": round(float(goals.value_ratio(r)), 2),
            } for r in ranked],
            "excluded": [{"id": r.id, "title": r.title, "reason": reason,
                          "reason_label": REASON_LABELS[reason]}
                         for r, reason in excluded],
        },
        "health": {
            "liability": None if li is None else dict(li.__dict__),
            "expiring_30d_points": (expiry.exposure(lots, now=now, horizon_days=30)
                                    if lots else None),
            "repurchase_90d": _rate_dict(rate(*repurchase)) if repurchase else None,
            "lift": _rate_dict(lift(**lift_counts)) if lift_counts else None,
        },
    }
