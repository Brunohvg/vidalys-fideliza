"""PR25 — gates financeiros e OAuth/HTTP somente com provedores sintéticos."""
import os
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.loyalty.models import LoyaltyRule, LoyaltyVoucher, VoucherPointAllocation
from apps.loyalty.services import _code_digests
from apps.participants.models import ProgramParticipant
from apps.customers.services import attach_verified_contact
from apps.sales.models import SaleRecord
from apps.loyalty.models import FinancialEvidence
from apps.points.models import PointEntry
from apps.wallets.models import CashbackEntry
from apps.points.models import PointLot, PointWallet
from apps.sales.models import DiscountRewardDraft
from apps.tenants.models import Tenant, TenantLoyaltyActivationAudit
from .coupon_client import CouponRemoteError, coupon_payload, create_coupon_once
from .coupon_service import PilotCouponBlocked, provision_coupon
from .models import NuvemshopInstallation, NuvemshopCouponIntent, NuvemshopOrderRecheck
from .order_recheck_service import recheck_order_event
from .order_webhook_models import OrderWebhookEvent
from .security import encrypt_token


class CouponResponse:
    status = 201

    def __init__(self, data):
        import json
        self.payload = json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit):
        return self.payload[:limit]


class CouponOpener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def open(self, request, timeout):
        self.request = request
        return CouponResponse(self.payload)


class CouponContractTests(SimpleTestCase):
    def test_provider_uses_official_fixed_host_max_one_use_and_exact_money(self):
        expected = coupon_payload(
            code="VF" + "A" * 24, discount_cents=2390,
            min_order_cents=10000, expires_at=timezone.now()+timedelta(days=1),
        )
        self.assertEqual(expected["type"], "absolute")
        self.assertEqual(expected["max_uses"], 1)
        self.assertEqual(expected["value"], "23.90")
        self.assertEqual(expected["min_price"], "100.00")
        self.assertFalse(expected["combines_with_other_discounts"])
        opener = CouponOpener({
            **expected, "id": 77990, "min_price": 100, "value": "23.90",
        })
        result = create_coupon_once(
            store_id="54321", token="synthetic-token-long-enough",
            agent="Vidalys Fideliza (test@example.invalid)",
            expected=expected, opener=opener,
        )
        self.assertEqual(result, "77990")
        self.assertEqual(opener.request.get_method(), "POST")
        self.assertEqual(opener.request.full_url,
                         "https://api.tiendanube.com/2025-03/54321/coupons")
        self.assertIn("Bearer synthetic-token", opener.request.get_header("Authorization"))
        with self.assertRaises(CouponRemoteError):
            coupon_payload(code="not a code", discount_cents=2390,
                           min_order_cents=10000, expires_at=timezone.now())


class PilotCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="pr25-pilot-admin", password="test-secret",
            email="admin@example.invalid",
        )
        self.qa = Tenant.objects.create(
            name="Loja QA independente", slug="qa-fideliza-pr25",
            status=Tenant.Status.ACTIVE,
        )
        self.commercial = Tenant.objects.create(
            name="Bibelô", slug="bibelo", status=Tenant.Status.ACTIVE,
        )
        self.options = {
            "actor_id": str(self.user.pk),
            "ticket": "QA-PR25-APPROVED",
            "approved_sha": "a" * 40,
        }

    def test_default_off_command_requires_approval_and_blocks_commercial_store(self):
        self.assertFalse(self.qa.loyalty_live_enabled)
        self.assertFalse(self.commercial.loyalty_live_enabled)
        with self.assertRaises(CommandError):
            call_command("set_loyalty_pilot", tenant_id=str(self.qa.pk),
                         enable=True, confirm="ENABLE_QA_ONLY", **self.options)
        with patch.dict(os.environ, {
            "FIDELIZA_ENVIRONMENT": "homolog",
            "FIDELIZA_PILOT_ACTIVATION_APPROVAL": "YES_VERIFIED_QA_ONLY",
        }):
            with self.assertRaises(CommandError):
                call_command("set_loyalty_pilot", tenant_id=str(self.commercial.pk),
                             enable=True, confirm="ENABLE_QA_ONLY", **self.options)
            call_command("set_loyalty_pilot", tenant_id=str(self.qa.pk),
                         enable=True, confirm="ENABLE_QA_ONLY", **self.options)
            self.qa.refresh_from_db()
            self.assertTrue(self.qa.loyalty_live_enabled)
            self.assertEqual(TenantLoyaltyActivationAudit.objects.count(), 1)
            call_command("set_loyalty_pilot", tenant_id=str(self.qa.pk),
                         disable=True, confirm="DISABLE_QA_ONLY", **self.options)
        self.qa.refresh_from_db()
        self.assertFalse(self.qa.loyalty_live_enabled)
        self.assertEqual(TenantLoyaltyActivationAudit.objects.count(), 2)


@override_settings(
    FIDELIZA_POINTS_WRITES_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=True,
    FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=True,
    FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"psp_test"}),
    FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=True,
)
class CouponIdempotencyTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Nuvemshop QA", slug="qa-coupon-pr25", status=Tenant.Status.ACTIVE,
            platform="nuvemshop", external_store_id="54321", loyalty_live_enabled=True,
        )
        user = get_user_model().objects.create_user(username="pr25-coupon-owner")
        self.participant = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Cliente QA", consent_at=timezone.now(),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE,
        )
        rule = LoyaltyRule.objects.create(
            tenant=self.tenant, version=1, enabled=True, budget_cents=100000,
        )
        reward = DiscountRewardDraft.objects.create(
            tenant=self.tenant, title="Cupom QA", points_cost=10,
            discount_cents=100, min_order_cents=1000, updated_by=user,
            publication_status=DiscountRewardDraft.PublicationStatus.PUBLISHED,
            published_at=timezone.now(), allowed_channels="nuvemshop",
        )
        self.code = "VF" + "A" * 24
        self.voucher = LoyaltyVoucher.objects.create(
            tenant=self.tenant, participant=self.participant, rule=rule,
            reward=reward, code_digest=_code_digests(self.code)[0],
            unit=LoyaltyVoucher.Unit.POINTS, amount=10, discount_cents=100,
            minimum_order_cents=1000, allowed_channels="nuvemshop",
            expires_at=timezone.now()+timedelta(days=3),
        )
        wallet = PointWallet.objects.create(
            tenant=self.tenant, participant=self.participant,
        )
        lot = PointLot.objects.create(
            tenant=self.tenant, wallet=wallet, channel="nuvemshop",
            source_reference="QA-COUPON-25", eligible_amount_cents=1000,
            source_paid_at=timezone.now(), verification_digest="b" * 64,
            rule_version="rule:1", points_issued=10, unlock_at=timezone.now(),
            expires_at=timezone.now()+timedelta(days=20),
        )
        VoucherPointAllocation.objects.create(
            voucher=self.voucher, lot=lot, amount=10,
        )
        self.fernet = Fernet.generate_key().decode()
        self.cfg = SimpleNamespace(
            client_id="12345", user_agent="Fideliza QA (qa@example.invalid)",
            token_keys=self.fernet,
        )
        NuvemshopInstallation.objects.create(
            tenant=self.tenant, client_id=self.cfg.client_id, store_id="54321",
            scope="read_orders,write_coupons",
            token_ciphertext=encrypt_token("synthetic-oauth-token-123", self.fernet),
        )

    def test_default_flag_blocks_outbound_even_if_tenant_flag_is_true(self):
        with override_settings(FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED=False):
            with patch("apps.nuvemshop.coupon_service.config", return_value=self.cfg):
                with self.assertRaises(PilotCouponBlocked):
                    provision_coupon(voucher_id=self.voucher.pk, issued_code=self.code)
        self.assertFalse(NuvemshopCouponIntent.objects.exists())

    def test_one_post_retry_only_get_and_encrypted_code(self):
        with patch("apps.nuvemshop.coupon_service.config", return_value=self.cfg), (
            patch("apps.nuvemshop.coupon_service.create_coupon_once", return_value="876")
        ) as posted, (
            patch("apps.nuvemshop.coupon_service.find_coupon_exact") as found
        ):
            intent, code = provision_coupon(
                voucher_id=self.voucher.pk, issued_code=self.code,
            )
            self.assertEqual(code, self.code)
            self.assertEqual(intent.state, NuvemshopCouponIntent.State.ISSUED)
            self.assertEqual(intent.remote_coupon_id, "876")
            self.assertNotIn(code, intent.encrypted_code)
            repeat, again = provision_coupon(
                voucher_id=self.voucher.pk, issued_code=self.code,
            )
            self.assertEqual(repeat.pk, intent.pk)
            self.assertEqual(again, self.code)
            posted.assert_called_once()
            found.assert_not_called()
        self.assertEqual(NuvemshopCouponIntent.objects.count(), 1)

    def test_timeout_creates_uncertain_intent_no_second_post(self):
        with patch("apps.nuvemshop.coupon_service.config", return_value=self.cfg), (
            patch("apps.nuvemshop.coupon_service.create_coupon_once",
                  side_effect=CouponRemoteError("timeout"))
        ) as posted, (
            patch("apps.nuvemshop.coupon_service.find_coupon_exact", return_value=None)
        ) as found:
            with self.assertRaises(PilotCouponBlocked):
                provision_coupon(voucher_id=self.voucher.pk, issued_code=self.code)
            intent = NuvemshopCouponIntent.objects.get()
            self.assertEqual(intent.state, intent.State.UNCERTAIN)
            with self.assertRaises(PilotCouponBlocked):
                provision_coupon(voucher_id=self.voucher.pk, issued_code=self.code)
            posted.assert_called_once()
            found.assert_called_once()

    @override_settings(
        FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=True,
        FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED=True,
        FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED=True,
    )
    def test_oauth_order_recheck_matches_coupon_but_never_redeems_without_psp(self):
        self.participant.contact_email = "pr25-buyer@example.invalid"
        self.participant.save(update_fields=["contact_email"])
        profile, _ = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            email=self.participant.contact_email, proof_method="email_otp",
        )
        with patch("apps.nuvemshop.coupon_service.config", return_value=self.cfg), (
            patch("apps.nuvemshop.coupon_service.create_coupon_once", return_value="876")
        ):
            provision_coupon(voucher_id=self.voucher.pk, issued_code=self.code)
        event = OrderWebhookEvent.objects.create(
            tenant=self.tenant, store_id="54321", order_id="9876",
            topic=OrderWebhookEvent.Topic.PAID, dedupe_key="c" * 64,
        )
        order = {
            "id": 9876, "store_id": 54321, "number": 111,
            "status": "open", "payment_status": "paid",
            "paid_at": timezone.now().isoformat(),
            "total": "19.90", "total_paid_by_customer": "19.90",
            "currency": "BRL", "gateway": "psp_test",
            "contact_email": self.participant.contact_email,
            "coupon_id": 876, "coupon": [{"id": 876, "code": self.code}],
            "discount_coupon": "1.00",
        }
        with patch("apps.nuvemshop.order_recheck_service.config", return_value=self.cfg), (
            patch("apps.nuvemshop.order_recheck_service.read_order", return_value=order)
        ) as read:
            state = recheck_order_event(event_id=event.pk)
            self.assertEqual(state, "applied_pending_independent_capture")
            self.assertEqual(recheck_order_event(event_id=event.pk), "already_checked")
            read.assert_called_once()
        intent = NuvemshopCouponIntent.objects.get(voucher=self.voucher)
        self.assertEqual(intent.state, intent.State.APPLIED)
        self.assertEqual(intent.order_id, "9876")
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.state, LoyaltyVoucher.State.RESERVED)
        sale = SaleRecord.objects.get(
            tenant=self.tenant, channel=SaleRecord.Channel.NUVEMSHOP,
            external_reference="9876",
        )
        self.assertEqual(sale.order_status, SaleRecord.OrderStatus.PAID)
        self.assertEqual(sale.customer_profile_id, profile.pk)
        self.assertEqual(sale.eligible_amount_cents, 0)
        self.assertEqual(NuvemshopOrderRecheck.objects.count(), 1)
        self.assertEqual(sale.inbound_events.count(), 1)
        self.assertFalse(FinancialEvidence.objects.exists())
        self.assertFalse(PointEntry.objects.exists())
        self.assertFalse(CashbackEntry.objects.exists())
