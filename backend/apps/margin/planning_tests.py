from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership

from .planning import plan_campaign


def scenario(**updates):
    data = {
        "eligible_subtotal_cents": 20000,
        "existing_discounts_cents": 1000,
        "cost_of_goods_cents": 10000,
        "payment_fee_cents": 500,
        "shipping_subsidy_cents": 1000,
        "other_variable_costs_cents": 500,
        "proposed_cashback_bps": 200,
        "minimum_margin_bps": 1500,
        "projected_paid_orders": 100,
        "campaign_budget_cents": 10000,
        "already_committed_cents": 2000,
    }
    data.update(updates)
    return data


class PlannerMathTests(SimpleTestCase):
    def test_budget_limit_rejects_overspend(self):
        plan = plan_campaign(scenario())
        self.assertEqual(plan["per_order_net_revenue_cents"], 19000)
        self.assertEqual(plan["per_order_cashback_cents"], 380)
        self.assertEqual(plan["available_campaign_budget_cents"], 8000)
        self.assertEqual(plan["projected_new_exposure_cents"], 38000)
        self.assertEqual(plan["projected_total_exposure_cents"], 40000)
        self.assertEqual(plan["estimated_order_capacity"], 21)
        self.assertEqual(plan["maximum_budget_rate_bps"], 42)
        self.assertEqual(plan["suggested_limit_rate_bps"], 42)
        self.assertFalse(plan["budget_within_limit"])
        self.assertTrue(plan["margin_within_target"])
        self.assertEqual(plan["status"], "campaign_budget_exceeded")
        self.assertFalse(plan["automatically_approved"])

    def test_within_limits_is_not_activation(self):
        plan = plan_campaign(scenario(campaign_budget_cents=50000))
        self.assertEqual(plan["status"], "within_limits")
        self.assertTrue(plan["budget_within_limit"])
        self.assertFalse(plan["automatically_approved"])

    def test_unknown_cost_never_suggests_rate(self):
        plan = plan_campaign(scenario(cost_of_goods_cents=None))
        self.assertEqual(plan["status"], "cost_unknown")
        self.assertIsNone(plan["suggested_limit_rate_bps"])
        self.assertIsNone(plan["per_order_contribution_after_cents"])

    def test_margin_unsafe_even_with_big_budget(self):
        plan = plan_campaign(scenario(
            proposed_cashback_bps=5000, campaign_budget_cents=900000,
        ))
        self.assertEqual(plan["status"], "cashback_exceeds_margin")
        self.assertFalse(plan["margin_within_target"])

    def test_committed_above_budget(self):
        plan = plan_campaign(scenario(
            campaign_budget_cents=1000, already_committed_cents=2000
        ))
        self.assertEqual(plan["status"], "budget_already_exceeded")
        self.assertIsNone(plan["suggested_limit_rate_bps"])
        self.assertEqual(plan["available_campaign_budget_cents"], 0)

    def test_no_incentive_has_unbounded_order_capacity_by_rewards(self):
        plan = plan_campaign(scenario(proposed_cashback_bps=0))
        self.assertEqual(plan["per_order_cashback_cents"], 0)
        self.assertIsNone(plan["estimated_order_capacity"])
        self.assertEqual(plan["status"], "within_limits")

    def test_min_margin_already_unmet(self):
        plan = plan_campaign(scenario(cost_of_goods_cents=18000))
        self.assertEqual(plan["status"], "margin_already_below_target")
        self.assertIsNone(plan["suggested_limit_rate_bps"])

    def test_rate_rounding_never_exceeds_budget(self):
        plan = plan_campaign(scenario(
            eligible_subtotal_cents=101, existing_discounts_cents=0,
            cost_of_goods_cents=0, payment_fee_cents=0,
            shipping_subsidy_cents=0, other_variable_costs_cents=0,
            minimum_margin_bps=0, projected_paid_orders=37,
            campaign_budget_cents=37, already_committed_cents=0
        ))
        limit = plan["suggested_limit_rate_bps"]
        issued_per_order = (101 * limit + 5000) // 10000
        self.assertLessEqual(issued_per_order * 37, 37)


class PlannerApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="planner-alpha", password="not-real-planner-password"
        )
        other = get_user_model().objects.create_user(
            username="planner-beta", password="not-real-planner-password"
        )
        self.store = Tenant.objects.create(name="Planejamento Alpha", slug="planner-alpha")
        self.other_store = Tenant.objects.create(name="Planejamento Beta", slug="planner-beta")
        TenantMembership.objects.create(
            tenant=self.store, user=self.user, role=TenantMembership.Role.OWNER
        )
        TenantMembership.objects.create(
            tenant=self.other_store, user=other, role=TenantMembership.Role.ADMIN
        )
        self.client = APIClient()

    def url(self, tenant):
        return reverse("campaign-plan-preview", kwargs={"tenant_id": tenant.pk})

    def test_anonymous_denied(self):
        response = self.client.post(self.url(self.store), scenario(), format="json")
        self.assertIn(response.status_code, (401, 403))

    def test_other_store_returns_404(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url(self.other_store), scenario(), format="json")
        self.assertEqual(response.status_code, 404)

    def test_preview_without_writes(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url(self.store), scenario(), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "campaign_budget_exceeded")
        self.assertEqual(response.data["suggested_limit_rate_bps"], 42)
        self.assertFalse(response.data["automatically_approved"])
        self.assertEqual(Tenant.objects.count(), 2)

    def test_invalid_volume_budget_and_margin(self):
        self.client.force_authenticate(user=self.user)
        for changes in [
            {"projected_paid_orders": 0},
            {"projected_paid_orders": 50001},
            {"campaign_budget_cents": -1},
            {"existing_discounts_cents": 20000},
            {"proposed_cashback_bps": 10001},
        ]:
            response = self.client.post(
                self.url(self.store), scenario(**changes), format="json"
            )
            self.assertEqual(response.status_code, 400, changes)
