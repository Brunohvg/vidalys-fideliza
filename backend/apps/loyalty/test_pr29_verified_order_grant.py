"""PR29: synthetic PSP proof + fresh OAuth order + per-SKU verified COGS."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.costs.models import CostItem
from apps.customers.services import attach_verified_contact
from apps.participants.models import ProgramParticipant
from apps.loyalty.models import (
    FinancialEvidence, VerifiedPaymentProof, LoyaltyRule, LoyaltyTier, LoyaltyGrant,
)
from apps.loyalty.payment_proof import apply_verified_capture, PaymentProofBlocked
from apps.loyalty.services import release_grant
from apps.nuvemshop.models import NuvemshopInstallation
from apps.points.services import wallet_balances
from apps.points.models import PointWallet
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant
from apps.wallets.models import CashbackEvent


@override_settings(
    FIDELIZA_POINTS_WRITES_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=True,
    FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=True,
    FIDELIZA_PAYMENT_PROOF_RECORDING_ENABLED=True,
    FIDELIZA_ORDER_LINE_COST_BINDING_VERIFIED=True,
    FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"pagarme_v5"}),
)
class VerifiedOrderGrantTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="pr29-cost-proof")
        now = timezone.now()
        self.tenant = Tenant.objects.create(
            name="QA order line proof", slug="qa-order-line-proof",
            status=Tenant.Status.ACTIVE, platform="nuvemshop",
            external_store_id="54321", loyalty_live_enabled=True,
        )
        self.participant = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="QA Shopper",
            contact_email="qa-pr29@example.invalid",
            consent_at=now-timedelta(days=1),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE,
        )
        ProgramParticipant.objects.filter(pk=self.participant.pk).update(
            joined_at=now-timedelta(days=1),
        )
        self.profile,_ = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            email=self.participant.contact_email, proof_method="email_otp",
        )
        self.sale = SaleRecord.objects.create(
            tenant=self.tenant, channel=SaleRecord.Channel.NUVEMSHOP,
            external_reference="901", reported_total_cents=2700,
            eligible_amount_cents=0, order_status=SaleRecord.OrderStatus.PAID,
            customer_profile=self.profile,
        )
        self.evidence = FinancialEvidence.objects.create(
            tenant=self.tenant, sale=self.sale, provider="pagarme_v5",
            external_event_id="pagarme_v5_get:ch_qa_pr29_12345",
            kind=FinancialEvidence.Kind.CAPTURE,
            amount_cents=2700, verification_digest="f"*64,
            occurred_at=now-timedelta(minutes=1), verified_at=now,
        )
        VerifiedPaymentProof.objects.create(
            tenant=self.tenant,evidence=self.evidence,
            proof_method="pagarme_v5_get",reference_digest="a"*64,
            captured_at=self.evidence.occurred_at,
        )
        rule=LoyaltyRule.objects.create(
            tenant=self.tenant,version=1,enabled=True,
            points_per_unit=1,points_per_cents=100,point_value_cents=1,
            cashback_bps=500,hold_days=0,validity_days=30,
            budget_cents=100000,minimum_margin_bps=1000,
        )
        LoyaltyTier.objects.create(
            rule=rule,name="Iniciante",minimum_spend_cents=0,
            multiplier_bps=10000,
        )
        self.one=CostItem.objects.create(
            tenant=self.tenant,reference="one",name="One",
            external_variant_id="201",sku="ABC-01",unit_cost_cents=400,
            selling_price_cents=1000,verified_at=now,verified_by=self.user,
        )
        self.two=CostItem.objects.create(
            tenant=self.tenant,reference="two",name="Two",
            external_variant_id="202",sku="ABC-02",unit_cost_cents=300,
            selling_price_cents=700,verified_at=now,verified_by=self.user,
        )
        NuvemshopInstallation.objects.create(
            tenant=self.tenant,store_id="54321",client_id="123",
            scope="read_orders",token_ciphertext="synthetic-never-used",
        )
        self.cfg=SimpleNamespace(client_id="123",user_agent="QA example.invalid",
                                 token_keys="synthetic-key")
        self.order={
            "id":901,"store_id":54321,"status":"open","payment_status":"paid",
            "currency":"BRL","products":[
                {"id":11,"product_id":101,"variant_id":201,
                 "sku":"ABC-01","price":"10.00","quantity":2},
                {"id":12,"product_id":102,"variant_id":202,
                 "sku":"ABC-02","price":"7.00","quantity":1},
            ],
            "subtotal":"27.00","discount":"3.00","discount_coupon":"2.00",
            "shipping_cost_owner":"8.00","shipping_cost_customer":"3.00",
            "total":"27.00",
        }

    def _capture(self, **changes):
        with (
            patch("apps.costs.order_item_cost_reconciliation.config",
                  return_value=self.cfg),
            patch("apps.costs.order_item_cost_reconciliation.decrypt_token",
                  return_value="synthetic-token-from-oauth"),
            patch("apps.costs.order_item_cost_reconciliation.read_order",
                  return_value={**self.order,**changes}) as get,
        ):
            grant, created=apply_verified_capture(
                evidence_id=self.evidence.pk,payment_fee_cents=50,
            )
        self.assertEqual(get.call_count,1)
        return grant,created

    def test_all_skus_and_proof_credit_net_amount_not_freight(self):
        grant,created=self._capture()
        self.assertTrue(created)
        self.assertEqual(grant.eligible_amount_cents,2400)
        self.assertEqual(grant.points_issued,24)
        self.assertEqual(grant.cashback_cents,120)
        self.assertEqual(grant.exposure_cents,144)
        self.assertEqual(grant.point_lot.eligible_amount_cents,2400)
        self.assertEqual(CashbackEvent.objects.count(),1)
        released,changed=release_grant(grant_id=grant.pk)
        self.assertTrue(changed)
        wallet=PointWallet.objects.get(tenant=self.tenant,participant=self.participant)
        self.assertEqual(wallet_balances(wallet)["available"],24)
        again,again_created=self._capture()
        self.assertFalse(again_created)
        self.assertEqual(again.pk,grant.pk)
        self.assertEqual(LoyaltyGrant.objects.count(),1)

    def test_forged_signed_quote_cannot_claim_more_spending_or_less_cogs(self):
        from dataclasses import replace
        from apps.costs.order_item_cost_reconciliation import (
            read_verified_nuvemshop_order_costs, verify_verified_quote, OrderItemCostBlocked,
        )
        with (
            patch("apps.costs.order_item_cost_reconciliation.config",
                  return_value=self.cfg),
            patch("apps.costs.order_item_cost_reconciliation.decrypt_token",
                  return_value="synthetic-token-from-oauth"),
            patch("apps.costs.order_item_cost_reconciliation.read_order",
                  return_value=self.order),
        ):
            quote=read_verified_nuvemshop_order_costs(
                sale=self.sale,payment_fee_cents=50)
        with self.assertRaises(OrderItemCostBlocked):
            verify_verified_quote(
                sale=self.sale,quote=replace(quote,eligible_net_cents=3000))
        with self.assertRaises(OrderItemCostBlocked):
            verify_verified_quote(
                sale=self.sale,quote=replace(quote,cogs_cents=50))
        self.two.unit_cost_cents=100
        self.two.save(update_fields=["unit_cost_cents"])
        with self.assertRaises(OrderItemCostBlocked):
            verify_verified_quote(sale=self.sale,quote=quote)

    def test_one_missing_variant_never_grants_any_money(self):
        self.two.delete()
        with (
            patch("apps.costs.order_item_cost_reconciliation.config",
                  return_value=self.cfg),
            patch("apps.costs.order_item_cost_reconciliation.decrypt_token",
                  return_value="synthetic-token-from-oauth"),
            patch("apps.costs.order_item_cost_reconciliation.read_order",
                  return_value=self.order),
            self.assertRaises(PaymentProofBlocked),
        ):
            apply_verified_capture(evidence_id=self.evidence.pk,
                                   payment_fee_cents=50)
        self.assertFalse(LoyaltyGrant.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())
        self.assertFalse(PointWallet.objects.exists())
