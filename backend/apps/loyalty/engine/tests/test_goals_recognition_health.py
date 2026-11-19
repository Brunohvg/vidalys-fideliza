from datetime import date, datetime, timedelta, timezone

import pytest

from apps.loyalty.engine.club_health import in_message_holdout, liability, lift, rate
from apps.loyalty.engine.goals import Reward, goal_message, margin_ranking, next_goal
from apps.loyalty.engine.recognition import detect, may_message
from apps.loyalty.engine.rules import Rule

RULE = Rule(points=1, per_cents=100, hold_days=7, validity_days=180)


def R(rid, cost_pts, value, cost, **kw):
    return Reward(rid, f"Prêmio {rid}", cost_pts, value, cost, **kw)


CATALOG = [
    R("desconto20", 400, 2000, 2000),       # razão 1,0
    R("brinde", 500, 4000, 1200),           # razão 3,33
    R("frete", 600, 2500, None),            # custo desconhecido
    R("vip", 3000, 30000, 10000),           # razão 3,0, mas longe
    R("esgotado", 450, 9000, 100, stock=0),
]


def test_unknown_cost_never_becomes_zero():
    ranked, excluded = margin_ranking(CATALOG + [R("gratis", 100, 500, 0)])
    assert [r.id for r in ranked] == ["brinde", "vip", "desconto20"]
    reasons = {r.id: why for r, why in excluded}
    assert reasons == {"frete": "custo_desconhecido", "esgotado": "indisponivel",
                       "gratis": "custo_zero_revisar"}


def test_goal_prefers_best_value_inside_nearest_window():
    goal = next_goal(350, CATALOG, RULE)
    # janela: desconto20(400), brinde(500), frete(600) -> brinde tem melhor razão
    assert goal.reward.id == "brinde"
    assert goal.missing_points == 150
    assert goal.missing_spend_cents == 15000
    assert goal.progress_percent == 70
    assert goal.margin_known and goal.redeemable_now == ()
    assert goal_message(goal) == "Faltam 150 pontos para Prêmio brinde — cerca de R$ 150,00 em compras."


def test_far_rewards_do_not_steal_the_goal():
    goal = next_goal(0, CATALOG, RULE)
    assert goal.reward.id != "vip"
    # Caso real visto na pré-visualização: 420 pts, kit a 80 pts e oficina (melhor razão) a 1.080 pts.
    catalog = [R("kit", 500, 4500, 1300), R("frete", 600, 2500, None), R("oficina", 1500, 12000, 3000)]
    goal = next_goal(420, catalog, RULE)
    assert goal.reward.id == "kit" and goal.missing_points == 80


def test_goal_falls_back_to_nearest_when_costs_unknown():
    goal = next_goal(10, [R("a", 100, 900, None), R("b", 200, 900, None)], RULE)
    assert goal.reward.id == "a" and not goal.margin_known


def test_everything_redeemable_and_empty_catalog():
    goal = next_goal(5000, CATALOG, RULE)
    assert goal.missing_points == 0 and goal.progress_percent == 100
    assert set(goal.redeemable_now) == {"desconto20", "brinde", "frete", "vip"}
    assert goal_message(goal).startswith("Você já pode trocar")
    assert next_goal(10, [R("x", 10, 10, 10, active=False)], RULE) is None
    with pytest.raises(ValueError):
        next_goal(-1, CATALOG, RULE)


def test_milestones_are_idempotent_by_key():
    found = detect(purchases=5, previous_purchases=2, redemptions=1, previous_redemptions=0,
                   joined_on=date(2025, 3, 1), today=date(2026, 3, 1),
                   level="Prata", previous_level="Bronze")
    assert [m.key for m in found] == ["purchases:3", "purchases:5", "redemption:first",
                                      "anniversary:2026", "level:Prata"]
    assert detect(purchases=5, previous_purchases=5, redemptions=1, previous_redemptions=1,
                  joined_on=date(2025, 3, 1), today=date(2026, 3, 2)) == []


def test_leap_day_anniversary_and_first_level_is_not_level_up():
    found = detect(purchases=0, previous_purchases=0, redemptions=0, previous_redemptions=0,
                   joined_on=date(2024, 2, 29), today=date(2025, 2, 28),
                   level="Bronze", previous_level=None)
    assert [m.key for m in found] == ["anniversary:2025"]


def test_frequency_cap():
    now = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)
    assert may_message(last_message_at=None, now=now)
    assert not may_message(last_message_at=now - timedelta(days=6), now=now)
    assert may_message(last_message_at=now - timedelta(days=7), now=now)


def test_liability_range_and_unknown_cost():
    li = liability(1000, CATALOG)
    # custo/ponto: desconto 5,0 · brinde 2,4 · vip 3,33 (esgotado e desconhecido fora)
    assert (li.low_cents, li.high_cents, li.basis) == (2400, 5000, "faixa")
    assert liability(1000, [R("f", 10, 10, None)]).basis == "custo_desconhecido"
    assert liability(0, CATALOG).basis == "sem_pontos"


def test_rate_requires_sample_and_returns_wilson_interval():
    assert rate(5, 10).status == "dados_insuficientes"
    r = rate(30, 100)
    assert r.status == "ok" and r.value == 0.3
    assert r.low == pytest.approx(0.2189, abs=1e-3) and r.high == pytest.approx(0.3958, abs=1e-3)
    with pytest.raises(ValueError):
        rate(11, 10)


def test_lift_never_claims_effect_without_evidence():
    assert lift(club_successes=40, club_total=50, control_successes=10, control_total=50
                ).status == "dados_insuficientes"
    assert lift(club_successes=33, club_total=100, control_successes=30, control_total=100
                ).status == "inconclusivo"
    strong = lift(club_successes=400, club_total=1000, control_successes=300, control_total=1000)
    assert strong.status == "positivo" and strong.low > 0
    assert lift(club_successes=200, club_total=1000, control_successes=300, control_total=1000
                ).status == "negativo"


def test_holdout_is_deterministic_and_close_to_requested_share():
    picks = [in_message_holdout(tenant_id="t1", participant_id=str(i), holdout_bps=1000, salt="exp1")
             for i in range(20000)]
    assert 0.09 < sum(picks) / len(picks) < 0.11
    assert picks[:50] == [in_message_holdout(tenant_id="t1", participant_id=str(i),
                                             holdout_bps=1000, salt="exp1") for i in range(50)]
    with pytest.raises(ValueError):
        in_message_holdout(tenant_id="t", participant_id="p", holdout_bps=6000, salt="s")
