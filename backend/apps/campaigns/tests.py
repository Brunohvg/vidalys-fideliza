from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership
from .models import CampaignDraft


class CampaignDraftTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="draft-owner")
        self.analyst = User.objects.create_user(username="draft-analyst")
        self.stranger = User.objects.create_user(username="draft-stranger")
        self.tenant = Tenant.objects.create(name="Loja piloto", slug="draft-tenant")
        self.other = Tenant.objects.create(name="Loja externa", slug="other-draft-tenant")
        TenantMembership.objects.create(tenant=self.tenant, user=self.owner, role="owner")
        TenantMembership.objects.create(tenant=self.tenant, user=self.analyst, role="analyst")
        TenantMembership.objects.create(tenant=self.other, user=self.stranger, role="owner")
        self.client = APIClient()
        self.payload = {
            "title": "Segunda compra de novembro",
            "goal": "second_purchase",
            "cashback_rate_bps": 200,
            "ticket_cents": 10000,
            "projected_paid_orders": 100,
            "budget_cents": 30000,
        }

    def list_url(self, tenant=None):
        return reverse("campaign-draft-list", kwargs={"tenant_id": tenant or self.tenant.id})

    def detail_url(self, draft, tenant=None):
        return reverse("campaign-draft-detail", kwargs={
            "tenant_id": tenant or self.tenant.id, "draft_id": draft.id,
        })

    def save(self):
        self.client.force_authenticate(self.owner)
        result = self.client.post(self.list_url(), self.payload, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        return result

    def test_auth_tenant_and_role(self):
        self.assertIn(self.client.get(self.list_url()).status_code, (401, 403))
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(self.list_url()).status_code, 404)
        self.assertEqual(self.client.post(self.list_url(), self.payload, format="json").status_code, 404)
        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.get(self.list_url()).status_code, 200)
        self.assertEqual(self.client.post(self.list_url(), self.payload, format="json").status_code, 403)

    def test_save_retrieve_and_update_without_activation(self):
        saved = self.save()
        self.assertEqual(saved.data["status"], "draft")
        self.assertEqual(saved.data["preview"]["credit_per_order_cents"], 200)
        self.assertEqual(saved.data["preview"]["max_exposure_cents"], 20000)
        self.assertFalse(saved.data["preview"]["exceeds_budget"])
        self.assertEqual(saved["Cache-Control"], "private, no-store")
        draft = CampaignDraft.objects.get()
        listed = self.client.get(self.list_url())
        self.assertEqual(len(listed.data["items"]), 1)
        self.assertFalse(listed.data["activation_available"])
        self.assertEqual(listed.data["items"][0]["id"], str(draft.id))

        newer = {**self.payload, "cashback_rate_bps": 500, "expected_version": 1}
        response = self.client.patch(self.detail_url(draft), newer, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["version"], 2)
        self.assertTrue(response.data["preview"]["exceeds_budget"])
        stale = self.client.patch(self.detail_url(draft), newer, format="json")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(CampaignDraft.objects.count(), 1)

    def test_forbidden_status_and_unknown_field(self):
        self.client.force_authenticate(self.owner)
        for invalid in ({**self.payload, "status": "active"}, {**self.payload, "approved": True},
                        {**self.payload, "tenant": str(self.other.id)}):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.client.post(self.list_url(), invalid, format="json").status_code, 400)
        self.assertEqual(CampaignDraft.objects.count(), 0)

    def test_bad_values_rejected_without_side_effects(self):
        self.client.force_authenticate(self.owner)
        for field, value in [
            ("cashback_rate_bps", 0), ("cashback_rate_bps", 1001),
            ("ticket_cents", 0), ("ticket_cents", -1),
            ("budget_cents", 0), ("projected_paid_orders", 50001),
            ("goal", "send_whatsapp"), ("title", "  "),
        ]:
            with self.subTest(field=field, value=value):
                result = self.client.post(self.list_url(), {**self.payload, field: value}, format="json")
                self.assertEqual(result.status_code, 400, result.data)
        self.assertEqual(CampaignDraft.objects.count(), 0)

    def test_cross_tenant_drafts_hidden_and_analyst_readonly(self):
        self.save()
        draft = CampaignDraft.objects.get()
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(self.detail_url(draft, tenant=self.other.id)).status_code, 404)
        self.client.force_authenticate(self.analyst)
        detail = self.client.get(self.detail_url(draft))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(self.client.patch(self.detail_url(draft), {
            **self.payload, "expected_version": 1,
        }, format="json").status_code, 403)
        self.assertEqual(self.client.delete(self.detail_url(draft)).status_code, 405)

    def test_limit_of_thirty_plans(self):
        self.client.force_authenticate(self.owner)
        for idx in range(30):
            result = self.client.post(
                self.list_url(), {**self.payload, "title": f"Rascunho {idx}"},
                format="json",
            )
            self.assertEqual(result.status_code, 201)
        result = self.client.post(self.list_url(), self.payload, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(CampaignDraft.objects.count(), 30)
