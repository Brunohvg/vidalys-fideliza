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
