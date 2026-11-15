"""Ciclo QA PR26 sem chamadas externas: earn -> cupom -> uso -> PSP -> redeem + earn."""
import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.loyalty.tests import LoyaltyFinancialTests
from apps.loyalty.models import LoyaltyGrant, LoyaltyVoucher, PaymentProofAudit
from apps.loyalty.services import issue_voucher, release_grant
from apps.nuvemshop.models import NuvemshopInstallation, NuvemshopCouponIntent
from apps.nuvemshop.order_webhook_models import OrderWebhookEvent
from apps.nuvemshop.coupon_service import provision_coupon
from apps.nuvemshop.order_recheck_service import recheck_order_event
from apps.nuvemshop.security import encrypt_token
from apps.points.services import lot_balances
from apps.sales.models import SaleRecord

from .settlement_orchestration import settle_qa_nuvemshop_checkout


@override_settings(
    FIDELIZA_POINTS_WRITES_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=True,
    FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=True,
    FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"psp_test", "pagarme_v5"}),
    FIDELIZA_PAYMENT_PROOF_ENABLED=True,
    FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True,
    FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED=True,
)
class FullQaCycleTests(TestCase):
    setUp = LoyaltyFinancialTests.setUp
    make_sale = LoyaltyFinancialTests.make_sale
    proof = LoyaltyFinancialTests.proof
    create_grant = LoyaltyFinancialTests.create_grant
    reward = LoyaltyFinancialTests.reward

    def test_realistic_qa_flow_is_idempotent_and_audited(self):
        self.tenant.slug = "qa-full-payment-cycle"
        self.tenant.platform = "nuvemshop"
        self.tenant.external_store_id = "54321"
        self.tenant.loyalty_live_enabled = True
        self.tenant.save(update_fields=[
            "slug", "platform", "external_store_id", "loyalty_live_enabled",
        ])
        _, original, _ = self.create_grant("EARN-ORIGINAL-26")
        release_grant(grant_id=original.pk)
        self.assertGreaterEqual(lot_balances(original.point_lot)["available"], 100)
        reward = self.reward(100, discount=100)
        reward.allowed_channels = "nuvemshop"
        reward.save(update_fields=["allowed_channels"])
        voucher, coupon_code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=reward.pk,
        )
        self.assertEqual(voucher.state, LoyaltyVoucher.State.RESERVED)
        self.assertEqual(lot_balances(original.point_lot)["reserved"], 100)
        token_keys = Fernet.generate_key().decode()
        cfg = SimpleNamespace(
            client_id="12345", user_agent="Fideliza QA (qa@example.invalid)",
            token_keys=token_keys,
        )
        NuvemshopInstallation.objects.create(
            tenant=self.tenant, client_id="12345", store_id="54321",
            scope="read_orders,write_coupons",
            token_ciphertext=encrypt_token("synthetic-oauth-token-abc123", token_keys),
        )
        with (
            patch("apps.nuvemshop.coupon_service.config", return_value=cfg),
            patch("apps.nuvemshop.coupon_service.create_coupon_once", return_value="876") as posted,
        ):
            intent, code = provision_coupon(
                voucher_id=voucher.pk, issued_code=coupon_code,
            )
        posted.assert_called_once()
        self.assertEqual(code, coupon_code)
        event = OrderWebhookEvent.objects.create(
            tenant=self.tenant, store_id="54321", order_id="9876",
            topic=OrderWebhookEvent.Topic.PAID,
            dedupe_key="d" * 64,
        )
        remote_order = {
            "id": 9876, "store_id": 54321, "number": 120,
            "status": "open", "payment_status": "paid",
            "paid_at": timezone.now().isoformat(),
            "total": "100.00", "total_paid_by_customer": "100.00",
            "currency": "BRL", "gateway": "pagarme",
            "contact_email": self.participant.contact_email,
            "coupon_id": 876, "coupon": [{"id": 876, "code": code}],
            "discount_coupon": "1.00",
        }
        with (
            patch("apps.nuvemshop.order_recheck_service.config", return_value=cfg),
            patch("apps.nuvemshop.order_recheck_service.read_order", return_value=remote_order) as reader,
        ):
            result = recheck_order_event(event_id=event.pk)
        self.assertEqual(result, "applied_pending_independent_capture")
        reader.assert_called_once()
        self.assertEqual(LoyaltyVoucher.objects.get(pk=voucher.pk).state, "reserved")
        sale = SaleRecord.objects.get(tenant=self.tenant,
                                      channel=SaleRecord.Channel.NUVEMSHOP,
                                      external_reference="9876")
        self.assertEqual(sale.eligible_amount_cents, 0)  # reported, not PSP proof
        remote_charge = {
            "id": "ch_PR26ABCDEF123456", "status": "paid",
            "amount": 10000, "paid_amount": 10000, "refunded_amount": 0,
            "payment_method": "credit_card", "currency": "BRL",
            "paid_at": timezone.now().isoformat(),
            "order": {"id": "or_PR26ABCDEF123456", "code": "9876"},
            "last_transaction": {
                "status": "captured", "success": True,
                "amount": 10000, "refunded_amount": 0,
            },
        }
        with (
            override_settings(FIDELIZA_PAYMENT_PROOF_STRICT_ORIGIN_ENABLED=True),
            patch.dict(os.environ, {
                "FIDELIZA_PAGARME_QA_SECRET": "synthetic-pagarme-secret-value",
                "FIDELIZA_PAGARME_QA_TENANT_ID": str(self.tenant.pk),
            }),
            patch("apps.loyalty.payment_proof.fetch_pagarme_charge", return_value=remote_charge) as fetched,
            patch("apps.nuvemshop.coupon_settlement.config", return_value=cfg),
        ):
            outcome = settle_qa_nuvemshop_checkout(
                intent_id=intent.pk,
                charge_id=remote_charge["id"],
                costs=self.costs,
            )
            replay = settle_qa_nuvemshop_checkout(
                intent_id=intent.pk,
                charge_id=remote_charge["id"],
                costs=self.costs,
            )
        self.assertEqual(fetched.call_count, 2)  # each retry rechecks PSP
        self.assertTrue(outcome["redeemed_now"])
        self.assertTrue(outcome["granted_now"])
        self.assertFalse(replay["redeemed_now"])
        self.assertFalse(replay["granted_now"])
        self.assertEqual(PaymentProofAudit.objects.count(), 1)
        self.assertEqual(LoyaltyGrant.objects.filter(sale=sale).count(), 1)
        voucher.refresh_from_db()
        self.assertEqual(voucher.state, "redeemed")
        self.assertEqual(voucher.redemption_sale_id, sale.pk)
        intent.refresh_from_db()
        self.assertEqual(intent.state, NuvemshopCouponIntent.State.SETTLED)
        self.assertEqual(lot_balances(original.point_lot)["reserved"], 0)
