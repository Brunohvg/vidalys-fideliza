from datetime import datetime, timedelta, timezone

import pytest

from apps.loyalty.engine.expiry import (
    ExpiringLot, days_left, effective_expiry, exposure, notice_message, plan_notices,
)
from apps.loyalty.engine.rules import Rule

BRT = timezone(timedelta(hours=-3))
T0 = datetime(2026, 1, 10, 12, 0, tzinfo=BRT)
FIXED = Rule(points=1, per_cents=100, hold_days=7, validity_days=180)
ROLLING = Rule(points=1, per_cents=100, hold_days=7, validity_days=90,
               expiry_policy="rolling", renewal_cap_days=365)


def test_fixed_ignores_activity():
    assert effective_expiry(FIXED, released_at=T0, activity=[T0 + timedelta(days=10)]) \
        == T0 + timedelta(days=180)


def test_rolling_renews_with_purchases_before_expiry():
    acts = [T0 + timedelta(days=80), T0 + timedelta(days=160)]
    assert effective_expiry(ROLLING, released_at=T0, activity=acts) == T0 + timedelta(days=250)


def test_rolling_does_not_revive_expired_points_and_ignores_older_activity():
    acts = [T0 - timedelta(days=5), T0 + timedelta(days=91)]
    assert effective_expiry(ROLLING, released_at=T0, activity=acts) == T0 + timedelta(days=90)


def test_rolling_is_capped_to_bound_liability():
    acts = [T0 + timedelta(days=d) for d in range(80, 800, 80)]
    assert effective_expiry(ROLLING, released_at=T0, activity=acts) == T0 + timedelta(days=365)


def test_requires_timezone():
    with pytest.raises(ValueError):
        effective_expiry(FIXED, released_at=datetime(2026, 1, 1))


def test_days_left_rounds_up():
    assert days_left(T0 + timedelta(hours=1), T0) == 1
    assert days_left(T0 + timedelta(days=7), T0) == 7
    assert days_left(T0 + timedelta(days=7, seconds=1), T0) == 8


def lot(pid, lid, pts, days):
    return ExpiringLot(pid, lid, pts, T0 + timedelta(days=days))


def test_one_consolidated_notice_per_participant_at_most_urgent_mark():
    lots = [lot("ana", "a1", 100, 25), lot("ana", "a2", 50, 6), lot("bia", "b1", 10, 40)]
    notices = plan_notices(lots, now=T0)
    assert len(notices) == 1
    ana = notices[0]
    assert ana.participant_id == "ana"
    assert ana.points == 150 and ana.offset_days == 7
    assert ana.dedupe_keys == ("a1:30", "a2:7")
    assert ana.earliest_expiry == T0 + timedelta(days=6)


def test_already_sent_marks_are_not_repeated_but_next_mark_fires():
    lots = [lot("ana", "a1", 100, 25)]
    assert plan_notices(lots, now=T0, already_sent={"a1:30"}) == []
    later = T0 + timedelta(days=19)
    notices = plan_notices(lots, now=later, already_sent={"a1:30"})
    assert notices[0].offset_days == 7


def test_ignores_expired_and_empty_lots():
    assert plan_notices([lot("ana", "a1", 0, 3), lot("ana", "a2", 9, -1)], now=T0) == []


def test_exposure_counts_window_only():
    lots = [lot("a", "1", 10, 5), lot("a", "2", 20, 30), lot("a", "3", 40, 31), lot("a", "4", 80, -1)]
    assert exposure(lots, now=T0, horizon_days=30) == 30


def test_message_is_short_and_actionable():
    notice = plan_notices([lot("ana", "a1", 1500, 1)], now=T0)[0]
    text = notice_message(notice, store_name="Bibelô", club_url="https://x/clube/bibelo")
    assert text.startswith("Bibelô: 1.500 pontos do seu clube vencem hoje")
    assert "11/01/2026" in text and text.endswith("https://x/clube/bibelo")
