from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership

from .services import simulate_margin


def payload(**changes):
    data = {
        "eligible_subtotal_cents": 20000,
        "existing_discounts_cents": 0,
        "cost_of_goods_cents": 10000,
        "payment_fee_cents": 500,
        "shipping_subsidy_cents": 1000,
        "other_variable_costs_cents": 500,
        "proposed_cashback_bps": 200,
        "minimum_margin_bps": 1500,
    }
    data.update(changes)
    return data


class MarginMathTests(SimpleTestCase):
    def test_contribution_and_safe_cashback(self):
        r = simulate_margin(payload())
        self.assertEqual(r["eligible_net_revenue_cents"], 20000)
        self.assertEqual(r["estimated_cashback_exposure_cents"], 400)
        self.assertEqual(r["contribution_before_cents"], 8000)
        self.assertEqual(r["contribution_after_cents"], 7600)
        self.assertEqual(r["margin_after_bps"], 3800)
        self.assertEqual(r["safe_cashback_budget_cents"], 5000)
        self.assertEqual(r["maximum_safe_cashback_bps"], 2500)
        self.assertEqual(r["status"], "within_target")
        self.assertFalse(r["automatically_approved"])

    def test_existing_discounts_reduce_eligible_base(self):
        r = simulate_margin(payload(existing_discounts_cents=2000))
        self.assertEqual(r["eligible_net_revenue_cents"], 18000)
        self.assertEqual(r["estimated_cashback_exposure_cents"], 360)
        self.assertEqual(r["contribution_before_cents"], 6000)
        self.assertEqual(r["contribution_after_cents"], 5640)

    def test_missing_cogs_never_looks_profitable(self):
        r = simulate_margin(payload(cost_of_goods_cents=None))
        self.assertEqual(r["status"], "cost_unknown")
        self.assertIsNone(r["contribution_after_cents"])
        self.assertIsNone(r["maximum_safe_cashback_bps"])

    def test_target_already_unmet_even_without_cashback(self):
        r = simulate_margin(payload(cost_of_goods_cents=17500, proposed_cashback_bps=0))
        self.assertEqual(r["status"], "margin_already_below_target")
        self.assertEqual(r["maximum_safe_cashback_bps"], 0)

    def test_cashback_above_safe_budget_is_blocked(self):
        r = simulate_margin(payload(proposed_cashback_bps=3000))
        self.assertEqual(r["status"], "cashback_exceeds_margin")
        self.assertEqual(r["estimated_cashback_exposure_cents"], 6000)

    def test_exact_floor_and_rounding(self):
        r = simulate_margin(payload(
            eligible_subtotal_cents=99, cost_of_goods_cents=98,
            payment_fee_cents=0, shipping_subsidy_cents=0,
            other_variable_costs_cents=0, proposed_cashback_bps=100,
            minimum_margin_bps=0,
        ))
        self.assertEqual(r["estimated_cashback_exposure_cents"], 1)
        self.assertEqual(r["status"], "within_target")
        self.assertEqual(r["contribution_after_cents"], 0)

    def test_max_safe_bps_never_exceeds_budget_due_to_rounding(self):
        r = simulate_margin(payload(
            eligible_subtotal_cents=99, cost_of_goods_cents=98,
            payment_fee_cents=0, shipping_subsidy_cents=0,
            other_variable_costs_cents=0, proposed_cashback_bps=200,
            minimum_margin_bps=0,
        ))
        self.assertEqual(r["safe_cashback_budget_cents"], 1)
        self.assertLessEqual((99 * r["maximum_safe_cashback_bps"] + 5000)//10000, 1)


class MarginApiTests(TestCase):
    def setUp(self):
        self.alice = get_user_model().objects.create_user(
            username="alice-margin", password="test-not-real"
        )
        self.bob = get_user_model().objects.create_user(
            username="bob-margin", password="test-not-real"
        )
        self.a = Tenant.objects.create(name="Loja A", slug="a-margin")
        self.b = Tenant.objects.create(name="Loja B", slug="b-margin")
        TenantMembership.objects.create(tenant=self.a, user=self.alice, role="owner")
        TenantMembership.objects.create(tenant=self.b, user=self.bob, role="owner")
        self.client = APIClient()

    def url(self, tenant):
        return reverse("tenant-margin-simulation", kwargs={"tenant_id": tenant.pk})

    def test_anonymous_user_cannot_simulate(self):
        self.assertIn(self.client.post(self.url(self.a), payload(), format="json").status_code, [401, 403])

    def test_cross_tenant_is_not_disclosed(self):
        self.client.force_authenticate(user=self.alice)
        self.assertEqual(self.client.post(self.url(self.b), payload(), format="json").status_code, 404)

    def test_authenticated_member_can_simulate_without_writes(self):
        self.client.force_authenticate(user=self.alice)
        r = self.client.post(self.url(self.a), payload(), format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "within_target")
        self.assertEqual(r.data["estimated_cashback_exposure_cents"], 400)
        self.assertFalse(r.data["automatically_approved"])
        self.assertEqual(Tenant.objects.count(), 2)

    def test_cost_is_required_for_margin_approval_but_not_for_preview(self):
        self.client.force_authenticate(user=self.alice)
        data = payload()
        data.pop("cost_of_goods_cents")
        r = self.client.post(self.url(self.a), data, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "cost_unknown")

    def test_reject_discount_greater_than_revenue(self):
        self.client.force_authenticate(user=self.alice)
        r = self.client.post(
            self.url(self.a), payload(existing_discounts_cents=20000), format="json"
        )
        self.assertEqual(r.status_code, 400)

    def test_reject_negative_values_and_rate_over_hundred(self):
        self.client.force_authenticate(user=self.alice)
        self.assertEqual(
            self.client.post(self.url(self.a), payload(cost_of_goods_cents=-1), format="json").status_code,
            400,
        )
        self.assertEqual(
            self.client.post(self.url(self.a), payload(proposed_cashback_bps=10001), format="json").status_code,
            400,
        )
