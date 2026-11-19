import json
from datetime import datetime, timedelta, timezone

from apps.loyalty.engine.expiry import ExpiringLot
from apps.loyalty.engine.goals import Reward
from apps.loyalty.engine.payloads import club_payload, merchant_payload
from apps.loyalty.engine.recognition import Milestone
from apps.loyalty.engine.rules import Rule

NOW = datetime(2026, 11, 17, 15, tzinfo=timezone.utc)
RULE = Rule(points=1, per_cents=100, hold_days=7, validity_days=180)
REWARDS = [
    Reward("cupom", "R$ 20 de desconto", 400, 2000, 2000),
    Reward("caderno", "Caderno artesanal", 500, 4000, 1200),
    Reward("frete", "Frete grátis", 600, 2500, None),
]


def test_club_payload_never_invents_numbers_when_ledger_is_off():
    data = club_payload(store_name="Loja", club_url="https://x/clube/loja", rule=RULE,
                        ledger_active=False, rewards=REWARDS, now=NOW,
                        balance={"available": 999})
    assert data["balance"] is None and data["goal"] is None and data["expiring"] is None
    assert {r["state"] for r in data["rewards"]} == {"em_preparacao"}
    json.dumps(data)


def test_club_payload_active():
    lots = [ExpiringLot("p", "l1", 120, NOW + timedelta(days=6)),
            ExpiringLot("p", "l2", 80, NOW + timedelta(days=90))]
    data = club_payload(store_name="Loja", club_url="https://x/clube/loja", rule=RULE,
                        ledger_active=True, rewards=REWARDS, now=NOW,
                        balance={"available": 350, "pending": 40}, lots=lots,
                        milestones=[Milestone("purchases:3", "3 compras", "Obrigado!")])
    assert data["balance"] == {"available": 350, "pending": 40}
    assert data["expiring"]["points"] == 120 and data["expiring"]["days_left"] == 6
    assert data["goal"]["reward_id"] == "caderno"
    assert data["goal"]["missing_spend_cents"] == 15000
    assert [r["state"] for r in data["rewards"]] == ["faltam", "faltam", "faltam"]
    assert data["milestones"][0]["key"] == "purchases:3"
    json.dumps(data)


def test_merchant_payload_shape():
    data = merchant_payload(rule=RULE, terms_text="curto", rewards=REWARDS, now=NOW,
                            points_outstanding=10_000, repurchase=(42, 120),
                            lift_counts={"club_successes": 42, "club_total": 120,
                                         "control_successes": 9, "control_total": 40})
    assert data["clarity"]["seal"] is False
    assert [r["id"] for r in data["margin"]["ranked"]] == ["caderno", "cupom"]
    assert data["margin"]["ranked"][0]["value_ratio"] == 3.33
    assert data["margin"]["excluded"][0]["reason"] == "custo_desconhecido"
    assert data["health"]["liability"] == {"low_cents": 24000, "high_cents": 50000, "basis": "faixa"}
    assert data["health"]["repurchase_90d"]["status"] == "ok"
    assert data["health"]["lift"]["status"] == "dados_insuficientes"
    json.dumps(data)
