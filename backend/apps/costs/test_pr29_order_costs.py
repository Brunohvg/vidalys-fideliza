"""PR29: never infer line-item profitability from a total or local cart."""
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.costs.models import CostItem
from apps.costs.order_item_cost_reconciliation import (
    reconcile_order_item_costs, OrderItemCostBlocked,
)


class ReconcileOrderItemTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="QA cost orders", slug="qa-cost-orders",
            platform="nuvemshop", external_store_id="54321",
            status=Tenant.Status.ACTIVE,
        )
        self.owner = get_user_model().objects.create_user(username="qa-cost-29")
        self.order = {
            "id":901, "store_id":54321, "status":"open",
            "payment_status":"paid","currency":"BRL",
            "products":[
                {"id":11,"product_id":101,"variant_id":201,"sku":"ABC-01",
                 "quantity":"2","price":"10.00"},
                {"id":12,"product_id":102,"variant_id":"202","sku":"ABC-02",
                 "quantity":1,"price":"7.00"},
            ],
            "subtotal":"27.00", "discount":"3.00",
            "discount_coupon":"2.00", "shipping_cost_owner":"8.00",
            "shipping_cost_customer":"3.00","total":"27.00",
        }

    def _cost(self, variant_id, sku, cost):
        return CostItem.objects.create(
            tenant=self.tenant, reference="cost-"+sku, sku=sku,
            external_variant_id=str(variant_id), name="item-"+sku,
            unit_cost_cents=cost, selling_price_cents=1000,
            verified_at=timezone.now(), verified_by=self.owner,
        )

    def quote(self, **changes):
        return reconcile_order_item_costs(
            order={**self.order, **changes},tenant=self.tenant,
            expected_order_id="901", expected_total_cents=2700,
            payment_fee_cents=50,
        )

    def test_two_skus_one_missing_cost_fails_closed(self):
        self._cost(201,"ABC-01",400)
        with self.assertRaisesRegex(OrderItemCostBlocked,"202"):
            self.quote()

    def test_two_skus_coupon_discount_and_merchant_shipping_exact_cents(self):
        first=self._cost(201,"ABC-01",400)
        second=self._cost(202,"ABC-02",300)
        quote=self.quote()
        self.assertEqual(quote.gross_subtotal_cents,2700)
        self.assertEqual(quote.discounts_cents,300)
        self.assertEqual(quote.eligible_net_cents,2400)
        self.assertEqual(quote.cogs_cents,1100)
        self.assertEqual(quote.shipping_subsidy_cents,500)
        self.assertEqual(quote.contribution_before_rewards_cents,750)
        self.assertEqual(quote.sale_total_cents,2700)
        self.assertEqual(quote.costs.lines,((first.pk,2),(second.pk,1)))
        self.assertEqual(quote.costs.shipping_subsidy_cents,500)
        self.assertEqual(len(quote.snapshot_digest),64)
        again=self.quote()
        self.assertEqual(again.snapshot_digest,quote.snapshot_digest)

    def test_wrong_sku_and_variant_or_forged_total_are_rejected(self):
        self._cost(201,"ABC-01",400)
        self._cost(202,"ABC-02",300)
        bad=[
            {"products":[{**self.order["products"][0],"sku":"WRONG"},
                         self.order["products"][1]]},
            {"products":[{**self.order["products"][0],"variant_id":303},
                         self.order["products"][1]]},
            {"discount":"2.99"},
            {"total":"26.99"},
            {"shipping_cost_owner":None},
            {"products":self.order["products"][:1]},
            {"products":[self.order["products"][0],self.order["products"][0]]},
        ]
        for change in bad:
            with self.subTest(change=change),self.assertRaises(OrderItemCostBlocked):
                self.quote(**change)

    def test_cross_tenant_cost_is_not_accepted(self):
        self._cost(201,"ABC-01",400)
        foreign=Tenant.objects.create(name="Foreign",slug="pr29-foreign")
        CostItem.objects.create(
            tenant=foreign, reference="out", external_variant_id="202",
            sku="ABC-02", unit_cost_cents=300, selling_price_cents=700,
            verified_at=timezone.now(), verified_by=self.owner,
        )
        with self.assertRaises(OrderItemCostBlocked):
            self.quote()

    def test_quantity_must_be_positive_and_no_missing_sku(self):
        self._cost(201,"ABC-01",400)
        self._cost(202,"ABC-02",300)
        for patch_line in ({"quantity":0},{"quantity":True},{"sku":None},
                           {"price":"1.001"},{"id":None}):
            with self.subTest(patch_line=patch_line),self.assertRaises(OrderItemCostBlocked):
                lines=[{**self.order["products"][0],**patch_line},
                       self.order["products"][1]]
                self.quote(products=lines)
