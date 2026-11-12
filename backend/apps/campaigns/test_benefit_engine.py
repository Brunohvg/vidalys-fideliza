"""Simulações são puras: não criam cashback, pontos nem vouchers."""
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership
from apps.wallets.models import CashbackWallet, CashbackEntry, CashbackEvent
from .benefit_engine import (
    BenefitRule, HypotheticalPurchase, estimate_cashback_cents,
    exposure_summary, simulate_benefit,
)
from .models import CampaignDraft


class PureBenefitEngineTests(SimpleTestCase):
    def rule(self, goal="second_purchase", budget_cents=2000):
        return BenefitRule(
            goal=goal, rate_bps=200,
            ticket_cents=10000, projected_paid_orders=10,
            budget_cents=budget_cents, version=1,
        )

    def scenario(self, **changes):
        return HypotheticalPurchase(
            **{
                **{"order_amount_cents": 15000, "prior_paid_orders": 1},
                **changes,
            }
        )

    def test_exact_second_purchase_and_budget(self):
        result = simulate_benefit(self.rule(), self.scenario())
        self.assertEqual(result["state"], "hypothetical_match")
        self.assertEqual(result["estimated_reward_cents"], 300)
        self.assertEqual(result["remaining_budget_cents"], 2000)
        self.assertEqual(result["forecast"]["max_exposure_cents"], 2000)
        self.assertFalse(result["credit_eligible"])
        self.assertEqual(result["ledger_writes_performed"], 0)
        self.assertFalse(result["activation_available"])
        not_second = simulate_benefit(self.rule(), self.scenario(prior_paid_orders=2))
        self.assertEqual(not_second["state"], "goal_not_met")
        self.assertEqual(not_second["estimated_reward_cents"], 0)

    def test_reactivation_and_recurrence_have_explicit_predicates(self):
        self.assertEqual(
            simulate_benefit(self.rule("reactivation"),
                             self.scenario(days_since_last_paid_order=59))["state"],
            "goal_not_met",
        )
        self.assertEqual(
            simulate_benefit(self.rule("reactivation"),
                             self.scenario(days_since_last_paid_order=60))["state"],
            "hypothetical_match",
        )
        self.assertEqual(
            simulate_benefit(self.rule("reactivation"),
                             self.scenario())["goal_failure_code"],
            "reactivation_requires_inactivity_days",
        )
        self.assertEqual(
            simulate_benefit(self.rule("recurrence"),
                             self.scenario(prior_paid_orders=2))["state"],
            "hypothetical_match",
        )

    def test_rounding_budgets_and_zero_amount_no_float(self):
        self.assertEqual(estimate_cashback_cents(99, 100), 1)
        self.assertEqual(estimate_cashback_cents(150, 100), 2)
        self.assertEqual(
            simulate_benefit(self.rule(), self.scenario(committed_budget_cents=1800))["state"],
            "budget_insufficient",
        )
        self.assertEqual(
            simulate_benefit(self.rule(), self.scenario(committed_budget_cents=2000))["remaining_budget_cents"],
            0,
        )
        self.assertTrue(exposure_summary(10000, 500, 10, 1000)["exceeds_budget"])
        tiny = BenefitRule("second_purchase", 1, 1, 1, 100, 1)
        self.assertEqual(
            simulate_benefit(tiny, self.scenario(order_amount_cents=1))["state"],
            "reward_below_one_cent",
        )

    def test_invalid_numbers_and_goals_fail_closed(self):
        for invalid in (-1, True, 1.2, "100", 1_000_000_001):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                simulate_benefit(self.rule(), self.scenario(order_amount_cents=invalid))
        with self.assertRaises(ValueError):
            simulate_benefit(self.rule(), self.scenario(prior_paid_orders=0, days_since_last_paid_order=3))
        with self.assertRaises(ValueError):
            simulate_benefit(self.rule("fictitious"), self.scenario())


class BenefitSimulationApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="benefit-owner")
        self.analyst = User.objects.create_user(username="benefit-analyst")
        self.stranger = User.objects.create_user(username="benefit-stranger")
        self.tenant = Tenant.objects.create(name="Lojista piloto", slug="benefit-draft")
        self.other = Tenant.objects.create(name="Lojista de fora", slug="benefit-other")
        TenantMembership.objects.create(
            tenant=self.tenant, user=self.owner, role="owner",
        )
        TenantMembership.objects.create(
            tenant=self.tenant, user=self.analyst, role="analyst",
        )
        TenantMembership.objects.create(
            tenant=self.other, user=self.stranger, role="owner",
        )
        self.draft = CampaignDraft.objects.create(
            tenant=self.tenant, title="Segunda compra",
            goal="second_purchase", cashback_rate_bps=200,
            ticket_cents=10000, projected_paid_orders=10,
            budget_cents=1000,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.url = reverse("benefit-simulate", kwargs={
            "tenant_id": self.tenant.pk, "draft_id": self.draft.pk,
        })
        self.payload = {
            "order_amount_cents": 15000,
            "prior_paid_orders": 1,
            "committed_budget_cents": 0,
        }

    def test_hypothetical_budget_and_no_side_effects(self):
        before = self.draft.updated_at
        first = self.client.post(self.url, self.payload, format="json")
        again = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data, again.data)
        self.assertEqual(first.data["estimated_reward_cents"], 300)
        self.assertTrue(first.data["hypothetical_goal_met"])
        self.assertEqual(first.data["mode"], "simulation_only")
        self.assertFalse(first.data["credit_eligible"])
        self.assertFalse(first.data["activation_available"])
        self.assertEqual(first["Cache-Control"], "private, no-store")
        self.assertEqual(CashbackWallet.objects.count(), 0)
        self.assertEqual(CashbackEvent.objects.count(), 0)
        self.assertEqual(CashbackEntry.objects.count(), 0)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.updated_at, before)

    def test_budget_and_scenarios(self):
        result = self.client.post(self.url, {
            **self.payload, "committed_budget_cents": 900,
        }, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["state"], "budget_insufficient")
        self.assertEqual(result.data["estimated_reward_cents"], 0)
        self.assertEqual(result.data["remaining_budget_cents"], 100)

    def test_tenant_roles_and_payload_validation(self):
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.post(self.url, self.payload, format="json").status_code, 404)
        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.post(self.url, self.payload, format="json").status_code, 200)
        for extra in (
            {"status": "active"},
            {"paid_order_id": 123},
            {"tenant_id": str(self.other.id)},
        ):
            result = self.client.post(self.url, {**self.payload, **extra}, format="json")
            self.assertEqual(result.status_code, 400)
        for bad in (
            {"prior_paid_orders": True},
            {"order_amount_cents": -1},
            {"prior_paid_orders": 0, "days_since_last_paid_order": 2},
            {"committed_budget_cents": -100},
        ):
            self.assertEqual(
                self.client.post(self.url, {**self.payload, **bad}, format="json").status_code,
                400,
            )
        self.assertEqual(self.client.get(self.url).status_code, 405)
