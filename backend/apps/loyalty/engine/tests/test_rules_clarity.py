import pytest

from apps.loyalty.engine import formatting as fmt
from apps.loyalty.engine.clarity import checklist, describe
from apps.loyalty.engine.goals import Reward
from apps.loyalty.engine.rules import Rule, minimum_spend_cents, points_for, rule_from_mapping

BASE = Rule(points=1, per_cents=100, hold_days=7, validity_days=180)
TERMS_OK = ("Regulamento do clube. Cada R$ 1,00 em compras confirmadas vale 1 ponto. "
            "Os pontos ficam pendentes por 7 dias, prazo de trocas e devoluções, e depois são "
            "liberados. Pontos liberados valem por 180 dias. Avisamos antes do vencimento. "
            "Compras canceladas ou devolvidas têm os pontos estornados.")


def reward(points_cost=500, cost=1200, active=True, rid="r1"):
    return Reward(rid, "Brinde", points_cost, 4000, cost, active=active)


def test_formatting_pt_br():
    assert fmt.brl(123456789) == "R$ 1.234.567,89"
    assert fmt.brl(5) == "R$ 0,05"
    assert fmt.brl(-100) == "-R$ 1,00"
    assert fmt.points(1) == "1 ponto"
    assert fmt.points(1500) == "1.500 pontos"
    assert fmt.points(1500, short=True) == "1.500 pts"
    assert fmt.days(1) == "1 dia"
    with pytest.raises(ValueError):
        fmt.brl(1.5)


def test_rule_limits_match_quote_validate_rule():
    with pytest.raises(ValueError):
        Rule(points=0, per_cents=100, hold_days=0, validity_days=1)
    with pytest.raises(ValueError):
        Rule(points=1, per_cents=99, hold_days=0, validity_days=1)
    with pytest.raises(ValueError):
        Rule(points=1, per_cents=100, hold_days=91, validity_days=1)
    with pytest.raises(ValueError):
        Rule(points=1, per_cents=100, hold_days=0, validity_days=180, renewal_cap_days=365)
    with pytest.raises(ValueError):
        rule_from_mapping({"points": 1, "per_cents": 100, "hold_days": 7,
                           "validity_days": 180, "bonus": 2})
    assert rule_from_mapping({"points": 1, "per_cents": 100, "hold_days": 7,
                              "validity_days": 180}) == BASE


def test_points_round_down_and_minimum_spend_is_exact_inverse():
    rule = Rule(points=3, per_cents=1000, hold_days=0, validity_days=30)
    assert points_for(rule, 999) == 2
    for wanted in range(0, 200):
        spend = minimum_spend_cents(rule, wanted)
        assert points_for(rule, spend) >= wanted
        if spend:
            assert points_for(rule, spend - 1) < wanted


def test_describe_is_concrete_and_consistent_with_engine():
    text = describe(BASE)
    assert text["headline"] == "Cada R$ 1,00 em compras vale 1 ponto."
    joined = " ".join(text["sentences"])
    assert "R$ 9,99 gera 9 pontos" in joined
    assert "pendentes por 7 dias" in joined
    assert "valem por 180 dias" in joined
    assert "30, 7 e 1 dias" in joined
    assert "R$ 100,00 gera 100 pontos" in joined


def test_describe_rolling_and_instant():
    rule = Rule(points=1, per_cents=100, hold_days=0, validity_days=90,
                expiry_policy="rolling", renewal_cap_days=365)
    joined = " ".join(describe(rule, notice_offsets=(1,))["sentences"])
    assert "disponíveis assim que" in joined
    assert "cada nova compra renova" in joined and "até 365 dias" in joined
    assert "Avisamos você 1 dia antes" in joined


def test_checklist_grants_seal_only_when_everything_required_passes():
    report = checklist(BASE, terms_text=TERMS_OK, rewards=[reward()])
    assert report.seal, report.pending
    assert report.as_dict()["seal"] is True


@pytest.mark.parametrize("terms", [
    TERMS_OK.replace("180", "XX"),
    TERMS_OK + " Prazo: [inserir prazo].",
    TERMS_OK + " TODO revisar",
    "curto demais 7 180",
])
def test_checklist_blocks_placeholders_and_short_terms(terms):
    report = checklist(BASE, terms_text=terms, rewards=[reward()])
    assert not report.seal


def test_checklist_requires_same_numbers_as_engine():
    terms = TERMS_OK.replace("180 dias", "seis meses")
    report = checklist(BASE, terms_text=terms, rewards=[reward()])
    item = {i.key: i for i in report.items}["regulamento_igual_ao_motor"]
    assert not item.ok and "180 dias" in item.detail
    # 1180 não pode passar por 180
    report = checklist(BASE, terms_text=terms + " código 1180", rewards=[reward()])
    assert not report.seal


def test_checklist_needs_published_reward_and_notices():
    assert not checklist(BASE, terms_text=TERMS_OK, rewards=[reward(active=False)]).seal
    assert not checklist(BASE, terms_text=TERMS_OK, rewards=[reward()], notice_offsets=()).seal
    detail = {i.key: i for i in checklist(
        BASE, terms_text=TERMS_OK, rewards=[reward(300), reward(500, rid="r2")]).items}
    assert "300 pontos" in detail["recompensa_publicada"].detail
    assert "gasto mínimo de R$ 300,00" in detail["recompensa_publicada"].detail


def test_short_validity_is_only_a_recommendation():
    rule = Rule(points=1, per_cents=100, hold_days=7, validity_days=60)
    terms = TERMS_OK.replace("180", "60")
    report = checklist(rule, terms_text=terms, rewards=[reward()])
    assert report.seal
    assert not {i.key: i for i in report.items}["validade_generosa"].ok
