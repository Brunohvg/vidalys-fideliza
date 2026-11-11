from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership
from .models import CostItem, CostAudit


class CostCatalogTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner-costs", password="placeholder-not-real")
        self.analyst = User.objects.create_user(username="analyst-costs", password="placeholder-not-real")
        self.other = User.objects.create_user(username="other-costs", password="placeholder-not-real")
        self.tenant = Tenant.objects.create(name="Loja A custos", slug="costs-a")
        self.foreign = Tenant.objects.create(name="Loja B custos", slug="costs-b")
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role="owner")
        TenantMembership.objects.create(user=self.analyst, tenant=self.tenant, role="analyst")
        TenantMembership.objects.create(user=self.other, tenant=self.foreign, role="owner")
        self.client = APIClient()
        self.data = {
            "reference": " a-001 ",
            "name": "Item de teste",
            "sku": " sku-A ",
            "external_variant_id": "55001",
            "unit_cost_cents": 700,
            "selling_price_cents": 2000,
        }

    def list_url(self, tenant=None):
        return reverse("cost-items", kwargs={"tenant_id": tenant or self.tenant.pk})

    def item_url(self, item, tenant=None):
        return reverse("cost-item-detail", kwargs={"tenant_id": tenant or self.tenant.pk, "item_id": item.pk})

    def history_url(self, item, tenant=None):
        return reverse("cost-item-history", kwargs={"tenant_id": tenant or self.tenant.pk, "item_id": item.pk})

    def login(self, user=None):
        self.client.force_authenticate(user=user or self.owner)

    def create(self, **overrides):
        return self.client.post(self.list_url(), {**self.data, **overrides}, format="json")

    def test_anonymous_cannot_list_or_write(self):
        self.assertIn(self.client.get(self.list_url()).status_code, [401, 403])
        self.assertIn(self.create().status_code, [401, 403])

    def test_create_is_manual_unverified_and_normalizes_keys(self):
        self.login()
        r = self.create()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["reference"], "A-001")
        self.assertEqual(r.data["sku"], "SKU-A")
        self.assertEqual(r.data["review_status"], "needs_review")
        self.assertIsNone(r.data["verified_at"])
        self.assertEqual(r.data["version"], 1)
        self.assertEqual(CostAudit.objects.count(), 1)
        self.assertEqual(CostAudit.objects.first().after["unit_cost_cents"], 700)

    def test_cannot_verify_without_provenance_or_cost(self):
        self.login()
        r = self.create(verify_cost=True)
        self.assertEqual(r.status_code, 400)
        r = self.create(unit_cost_cents=None, verify_cost=True, provenance="Conferido em nota")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(CostItem.objects.count(), 0)

    def test_verify_and_prevent_silent_reuse_when_cost_changes(self):
        self.login()
        r = self.create(verify_cost=True, provenance="Conferido na NF de teste 001")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["review_status"], "ready_for_simulation")
        item = CostItem.objects.get(pk=r.data["id"])
        self.assertIsNotNone(item.verified_at)
        change = self.client.patch(
            self.item_url(item), {"expected_version": 1, "unit_cost_cents": 900}, format="json"
        )
        self.assertEqual(change.status_code, 200, change.data)
        self.assertEqual(change.data["review_status"], "needs_review")
        self.assertEqual(change.data["version"], 2)
        self.assertIsNone(change.data["verified_at"])
        self.assertEqual(CostAudit.objects.count(), 2)
        self.assertEqual(CostAudit.objects.order_by("created_at").first().after["version"], 1)
        self.assertEqual(CostAudit.objects.order_by("created_at").last().before["version"], 1)

    def test_update_requires_version_and_rejects_stale_changes(self):
        self.login()
        item_id = self.create().data["id"]
        item = CostItem.objects.get(pk=item_id)
        self.assertEqual(self.client.patch(self.item_url(item), {"name":"Alterado"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(
            self.item_url(item), {"expected_version": 0, "name": "Alterado"}, format="json"
        ).status_code, 400)
        changed = self.client.patch(self.item_url(item), {"expected_version": 1, "name": "Novo nome"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(changed.data["version"], 2)
        self.assertEqual(self.client.patch(
            self.item_url(item), {"expected_version": 1, "name": "Perdido"}, format="json"
        ).status_code, 409)
        item.refresh_from_db()
        self.assertEqual(item.name, "Novo nome")

    def test_update_only_price_does_not_reset_verified_cost(self):
        self.login()
        item_id = self.create(verify_cost=True, provenance="Conferido no relatório 55").data["id"]
        item = CostItem.objects.get(pk=item_id)
        before = item.verified_at
        r = self.client.patch(self.item_url(item), {"expected_version":1,"selling_price_cents":2500}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["review_status"], "ready_for_simulation")
        item.refresh_from_db()
        self.assertEqual(item.verified_at, before)

    def test_missing_cost_never_becomes_zero_or_verified(self):
        self.login()
        r = self.create(unit_cost_cents=None)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["review_status"], "missing_cost")
        self.assertIsNone(r.data["unit_cost_cents"])
        self.assertEqual(self.create(unit_cost_cents=0, reference="A-002", external_variant_id="2").status_code, 400)

    def test_analyst_can_read_but_cannot_write(self):
        self.login()
        r = self.create()
        item = CostItem.objects.get(pk=r.data["id"])
        self.login(self.analyst)
        self.assertEqual(self.client.get(self.list_url()).status_code, 200)
        self.assertEqual(self.client.get(self.item_url(item)).status_code, 200)
        self.assertEqual(self.client.get(self.history_url(item)).status_code, 200)
        self.assertEqual(self.create(reference="A-ANALYST", external_variant_id="501").status_code, 403)
        self.assertEqual(self.client.patch(
            self.item_url(item), {"expected_version":1,"name":"Tentativa"}, format="json"
        ).status_code, 403)
        self.assertEqual(CostItem.objects.count(), 1)

    def test_other_tenant_and_nonexistent_item_404(self):
        self.login()
        item = CostItem.objects.get(pk=self.create().data["id"])
        self.login(self.other)
        self.assertEqual(self.client.get(self.list_url()).status_code, 404)
        self.assertEqual(self.client.get(self.item_url(item)).status_code, 404)
        self.assertEqual(self.client.get(self.history_url(item)).status_code, 404)
        self.assertEqual(self.client.post(self.list_url(), self.data, format="json").status_code, 404)
        self.assertEqual(self.client.patch(self.item_url(item), {"expected_version":1, "name":"Ataque"}, format="json").status_code, 404)

    def test_duplicate_reference_or_variant_rejected_per_tenant(self):
        self.login()
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create().status_code, 409)
        self.assertEqual(self.create(reference="A-002").status_code, 409)
        self.assertEqual(CostItem.objects.count(), 1)
        self.login(self.other)
        r = self.client.post(
            self.list_url(self.foreign.pk), self.data, format="json"
        )
        self.assertEqual(r.status_code, 201)

    def test_search_summary_and_status_filter(self):
        self.login()
        self.create()
        self.create(reference="B-002", sku="SKU-B", name="Sem custo", external_variant_id="55002", unit_cost_cents=None)
        self.create(reference="C-003", sku="SKU-C", name="Conferido", external_variant_id="55003", verify_cost=True, provenance="Conferido NF teste 3")
        r = self.client.get(self.list_url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["summary"]["total"], 3)
        self.assertEqual(r.data["summary"]["missing_cost"], 1)
        self.assertEqual(r.data["summary"]["needs_review"], 1)
        self.assertEqual(r.data["summary"]["ready"], 1)
        filtered = self.client.get(self.list_url()+"?status=missing_cost")
        self.assertEqual(filtered.data["total_filtered"], 1)
        self.assertEqual(filtered.data["items"][0]["name"], "Sem custo")
        searched = self.client.get(self.list_url()+"?q=sku-a")
        self.assertEqual(searched.data["total_filtered"], 1)
        self.assertEqual(self.client.get(self.list_url()+"?limit=200").status_code, 400)
        self.assertEqual(self.client.get(self.list_url()+"?status=unknown").status_code, 400)

    def test_saving_changes_without_reference_field_works(self):
        self.login()
        item = CostItem.objects.get(pk=self.create().data["id"])
        response = self.client.patch(self.item_url(item), {"expected_version":1,"name":"Renomeado"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["reference"], "A-001")

    def test_remapping_sku_revokes_old_verification(self):
        self.login()
        item = CostItem.objects.get(pk=self.create(
            verify_cost=True, provenance="Custo conferido para SKU original"
        ).data["id"])
        r = self.client.patch(
            self.item_url(item), {"expected_version": 1, "sku": "SKU-NOVA"}, format="json"
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["review_status"], "needs_review")
        self.assertIsNone(r.data["verified_at"])

    def test_changing_provenance_revokes_verification(self):
        self.login()
        item = CostItem.objects.get(pk=self.create(
            verify_cost=True, provenance="Origem da conferência inicial"
        ).data["id"])
        r = self.client.patch(
            self.item_url(item), {"expected_version": 1, "provenance": "Outra origem ainda sem conferência"},
            format="json"
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["review_status"], "needs_review")
        self.assertIsNone(r.data["verified_at"])

    def test_remap_and_verify_same_request_requires_fresh_evidence(self):
        self.login()
        item = CostItem.objects.get(pk=self.create(
            verify_cost=True, provenance="Nota antiga de custo"
        ).data["id"])
        r = self.client.patch(
            self.item_url(item),
            {"expected_version": 1, "external_variant_id": "88771",
             "verify_cost": True, "provenance": "Nova nota de conferência para variante"},
            format="json"
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["review_status"], "ready_for_simulation")
        self.assertEqual(r.data["external_variant_id"], "88771")
