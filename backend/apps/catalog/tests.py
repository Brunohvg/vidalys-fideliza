from django.test import SimpleTestCase

from .reconciliation import InvalidSnapshot, reconcile_products


class Local:
    def __init__(self, ident, sku="", external_variant_id="", cost=1200, price=2990, verified=True):
        self.pk = ident
        self.reference = "REF-" + str(ident)
        self.sku = sku
        self.external_variant_id = external_variant_id
        self.unit_cost_cents = cost
        self.selling_price_cents = price
        self.verified_at = "2026-11-11" if verified else None


def products(*variants):
    return [{"id": 101, "name": {"pt": "Fita vermelha"}, "variants": list(variants) or [
        {"id": 2001, "sku": "FITA", "barcode": "07800001999",
         "price": "29.90", "promotional_price": "25.00", "cost": None},
    ]}]


class MappingTests(SimpleTestCase):
    def test_new_item_missing_cost_and_barcode_preserved(self):
        result = reconcile_products(products(), [])
        row = result["items"][0]
        self.assertEqual(row["barcode"], "07800001999")
        self.assertEqual(row["decision"], "unmapped")
        self.assertEqual(row["price_cents"], 2990)
        self.assertEqual(row["promotional_price_cents"], 2500)
        self.assertIsNone(row["api_cost_cents"])
        self.assertEqual(result["summary"]["missing_api_cost"], 1)
        self.assertEqual(result["writes_performed"], 0)

    def test_exact_variant_matches(self):
        result = reconcile_products(products({"id": 2001, "sku": "FITA",
            "price": "29.90", "cost": "12.00"}),
            [Local(1, sku="FITA", external_variant_id="2001")])
        self.assertEqual(result["items"][0]["decision"], "matched")

    def test_recreated_variant_not_auto_mapped_by_sku(self):
        result = reconcile_products(products({"id": 2999, "sku": "FITA",
            "price": "29.90"}), [Local(1, sku="FITA", external_variant_id="2001")])
        self.assertEqual(result["items"][0]["decision"], "review_required")
        self.assertIn("variant_id_changed", result["items"][0]["issues"])

    def test_ambiguous_sku_requires_review(self):
        result = reconcile_products(products({"id": 2999, "sku": "FITA",
            "price": "29.90"}), [Local(1, sku="FITA"), Local(2, sku="FITA")])
        self.assertEqual(result["items"][0]["decision"], "review_required")
        self.assertIn("ambiguous_local_sku", result["items"][0]["issues"])

    def test_cost_conflict_keeps_manual_cost(self):
        result = reconcile_products(products({"id": 2001, "sku": "FITA",
            "price": "29.90", "cost": "15.00"}),
            [Local(1, sku="FITA", external_variant_id="2001")])
        row = result["items"][0]
        self.assertEqual(row["decision"], "review_required")
        self.assertEqual(row["local_cost_cents"], 1200)
        self.assertEqual(row["api_cost_cents"], 1500)

    def test_duplicates_flagged(self):
        result = reconcile_products(products(
            {"id": 2001, "sku": "FITA", "price": "29.90"},
            {"id": 2002, "sku": "FITA", "price": "20.00"},
        ), [])
        self.assertEqual(result["summary"]["review_required"], 2)

    def test_invalid_values_rejected(self):
        for variant in [
            {"id": "bad", "price": "10.00"},
            {"id": 2, "barcode": 7890001, "price": "10.00"},
            {"id": 2, "price": "19.999"},
            {"id": 2, "price": -1},
            {"id": 2, "price": float("nan")},
        ]:
            with self.subTest(variant=variant), self.assertRaises(InvalidSnapshot):
                reconcile_products(products(variant), [])

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.costs.models import CostItem, CostAudit
from apps.tenants.models import Tenant, TenantMembership


class PreviewApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="preview-owner", password="test-pass-only")
        self.analyst = User.objects.create_user(username="preview-analyst", password="test-pass-only")
        self.other = User.objects.create_user(username="preview-other", password="test-pass-only")
        self.tenant = Tenant.objects.create(name="Alpha", slug="preview-a")
        self.foreign = Tenant.objects.create(name="Beta", slug="preview-b")
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role="owner")
        TenantMembership.objects.create(user=self.analyst, tenant=self.tenant, role="analyst")
        TenantMembership.objects.create(user=self.other, tenant=self.foreign, role="owner")
        self.item = CostItem.objects.create(
            tenant=self.tenant, reference="REF-1", name="Fita",
            sku="FITA", external_variant_id="2001", unit_cost_cents=1200,
            selling_price_cents=2990,
        )
        self.client = APIClient()

    def url(self, tenant=None):
        return reverse("catalog-reconcile-preview", kwargs={
            "tenant_id": tenant or self.tenant.pk
        })

    def test_anonymous_rejected(self):
        self.assertIn(self.client.post(self.url(), {"products": products()}, format="json").status_code, (401, 403))

    def test_foreign_tenant_hidden(self):
        self.client.force_authenticate(user=self.other)
        self.assertEqual(
            self.client.post(self.url(), {"products": products()}, format="json").status_code, 404
        )

    def test_analyst_preview_does_not_mutate_costs(self):
        self.client.force_authenticate(user=self.analyst)
        before = self.item.snapshot()
        r = self.client.post(self.url(), {"products": products()}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["items"][0]["local_item_id"], str(self.item.id))
        self.assertEqual(r.data["writes_performed"], 0)
        self.item.refresh_from_db()
        self.assertEqual(self.item.snapshot(), before)
        self.assertEqual(CostAudit.objects.count(), 0)

    def test_other_tenant_costs_never_leak(self):
        CostItem.objects.create(
            tenant=self.foreign, reference="REF-X", name="Outro",
            sku="OUTRO", external_variant_id="5005", unit_cost_cents=1234,
        )
        self.client.force_authenticate(user=self.owner)
        r = self.client.post(self.url(), {"products": products({
            "id": 5005, "sku": "OUTRO", "price": "40.00"
        })}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["items"][0]["local_item_id"])
        self.assertIsNone(r.data["items"][0]["local_cost_cents"])

    def test_invalid_or_oversized_input_rejected(self):
        self.client.force_authenticate(user=self.owner)
        for payload in [
            {"products": []},
            {"products": products(), "arbitrary_extra_field": 1},
            {"products": "not-list"},
        ]:
            self.assertEqual(self.client.post(self.url(), payload, format="json").status_code, 400)
        huge = products()
        huge[0]["name"] = "x" * 151000
        self.assertEqual(
            self.client.post(self.url(), {"products": huge}, format="json").status_code, 413
        )

import io
import json
from urllib.error import HTTPError
from .client import CatalogReadError, read_products_page


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return None

    def read(self, size):
        return self.data[:size]


class FakeTransport:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.requests = []

    def open(self, request, timeout=8):
        self.requests.append((request, timeout))
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)


class ReadClientTests(SimpleTestCase):
    def test_get_uses_fixed_host_and_get_only(self):
        fake = FakeTransport([[{"id": 10}]])
        rows = read_products_page(
            store_id=1234, access_token="synthetic-only",
            user_agent="Fideliza QA (qa@example.invalid)", opener=fake,
        )
        self.assertEqual(rows[0]["id"], 10)
        req, timeout = fake.requests[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(
            req.full_url,
            "https://api.tiendanube.com/2025-03/1234/products?page=1&per_page=15",
        )
        self.assertEqual(timeout, 8)

    def test_retries_on_429_without_leaking_response(self):
        error = HTTPError("internal", 429, "too many", {}, io.BytesIO(b"private"))
        fake = FakeTransport([error, [{"id": 11}]])
        pauses = []
        rows = read_products_page(
            store_id=1234, access_token="synthetic-only",
            user_agent="Fideliza QA (qa@example.invalid)",
            opener=fake, pause=lambda value: pauses.append(value),
        )
        self.assertEqual(rows[0]["id"], 11)
        self.assertEqual(pauses, [1])

    def test_errors_avoid_sensitive_body(self):
        fake = FakeTransport([HTTPError("internal", 403, "unauthorized", {}, io.BytesIO(b"private"))])
        with self.assertRaises(CatalogReadError) as caught:
            read_products_page(
                store_id=1234, access_token="synthetic-only",
                user_agent="Fideliza QA (qa@example.invalid)", opener=fake,
            )
        self.assertNotIn("private", str(caught.exception))
        self.assertNotIn("synthetic-only", str(caught.exception))

    def test_rejects_invalid_store_and_excessive_pages(self):
        for kwargs in ({"store_id": 0}, {"page": 0}, {"per_page": 200}):
            args = {"store_id": 1234, "access_token": "synthetic-only",
                    "user_agent": "Fideliza QA (qa@example.invalid)"}
            args.update(kwargs)
            with self.assertRaises(ValueError):
                read_products_page(**args, opener=FakeTransport([]))
