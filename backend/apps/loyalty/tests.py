"""PR20: financial engine remains blocked in production; tests use synthetic PSP facts."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.channels.serializers import OrderEventSerializer
from apps.channels.services import ingest_order_event
from apps.costs.models import CostItem
from apps.customers.services import attach_verified_contact
from apps.customers.models import CustomerProfile
from apps.participants.models import ProgramParticipant
from apps.points.models import PointEvent, PointLot
from apps.points.services import lot_balances, wallet_balances as point_balances
from apps.sales.models import DiscountRewardDraft, SaleRecord
from apps.tenants.models import Tenant
from apps.wallets.models import CashbackEvent, CashbackWallet
from apps.wallets.services import origin_balances, wallet_balances as cashback_balances

from .models import (
    FinancialEvidence, LoyaltyGrant, LoyaltyRecovery, LoyaltyRule, LoyaltyTier,
    LoyaltyVoucher, MemberTierSnapshot, VoucherPointAllocation, LoyaltyEngagement,
)
from .services import (
    LoyaltyBlocked, OrderCosts, calculate_reward, choose_tier,
    grant_for_captured_sale, issue_voucher, release_grant, redeem_voucher,
    reverse_grant, cancel_voucher, sale_readiness, verify_voucher,
    record_engagement_eligibility,
)

from .tasks import release_due_grants, scan_winback, reconcile_verified_refunds, scan_verified_birthdays


@override_settings(
    FIDELIZA_POINTS_WRITES_ENABLED=True,
    FIDELIZA_LEDGER_WRITES_ENABLED=True,
    FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=True,
    FIDELIZA_TRUSTED_PAYMENT_ADAPTERS=frozenset({"psp_test"}),
    SECURE_SSL_REDIRECT=False,  # HTTP test client; proxy HTTPS has a separate smoke
)
class LoyaltyFinancialTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.tenant = Tenant.objects.create(
            name="Loyalty QA", slug="loyalty-pr20", status=Tenant.Status.ACTIVE,
        )
        self.another_tenant = Tenant.objects.create(
            name="Outra loja", slug="loyalty-outro", status=Tenant.Status.ACTIVE,
        )
        self.owner = get_user_model().objects.create_user(username="owner-pr23-loyalty")
        self.participant = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Pessoa com adesão",
            contact_email="pessoa@example.com",
            consent_at=now - timedelta(days=90),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE,
        )
        ProgramParticipant.objects.filter(pk=self.participant.pk).update(
            joined_at=now - timedelta(days=90),
        )
        self.participant.refresh_from_db()
        self.profile, _ = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            email=self.participant.contact_email, proof_method="email_otp",
        )
        self.cost = CostItem.objects.create(
            tenant=self.tenant, reference="PR20-SKU-A",
            sku="SKU-A", name="Produto fictício", unit_cost_cents=3000,
            selling_price_cents=10000, verified_at=now,
            provenance="Amostra sintética validada",
        )
        self.rule = LoyaltyRule.objects.create(
            tenant=self.tenant, version=1, enabled=True,
            points_per_unit=1, points_per_cents=100,
            cashback_bps=500, point_value_cents=1,
            hold_days=0, validity_days=180,
            minimum_margin_bps=1000, budget_cents=100000,
            second_purchase_window_days=15, second_purchase_multiplier_bps=20000,
        )
        self.bronze = LoyaltyTier.objects.create(
            rule=self.rule, name="Bronze", minimum_spend_cents=0, multiplier_bps=10000,
        )
        self.gold = LoyaltyTier.objects.create(
            rule=self.rule, name="Ouro", minimum_spend_cents=15000, multiplier_bps=15000,
        )
        self.costs = OrderCosts(
            lines=((self.cost.pk, 1),),
            payment_fee_cents=200,
            shipping_subsidy_cents=100,
        )

    def reward(self, amount, *, unit="points", discount=None, max_redemptions=100):
        return DiscountRewardDraft.objects.create(
            tenant=self.tenant, title=f"Recompensa {unit} {amount}",
            points_cost=amount, discount_cents=discount if discount is not None else amount,
            min_order_cents=max(100, discount if discount is not None else amount),
            max_redemptions=max_redemptions,
            redemption_unit=unit, allowed_channels="counter,vidalys_flow",
            publication_status=DiscountRewardDraft.PublicationStatus.PUBLISHED,
            published_at=timezone.now(), updated_by=self.owner,
        )

    def redemption_evidence(self, ref):
        sale = self.make_sale(ref, channel="counter")
        return sale, self.proof(sale, minutes=0)

    def make_sale(self, ref, *, channel="vidalys_flow", status="paid", total="100.00"):
        payload = {
            "tenant_id": str(self.tenant.pk), "channel": channel,
            "external_order_id": ref,
            "customer_identifier": self.participant.contact_email,
            "total_amount": total, "currency": "BRL",
            "status": status, "source_event_id": "evt-" + ref,
        }
        serializer = OrderEventSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return ingest_order_event(data=serializer.validated_data).sale

    def proof(self, sale, *, kind="capture", minutes=10, provider="psp_test"):
        when = timezone.now() - timedelta(minutes=minutes)
        return FinancialEvidence.objects.create(
            tenant=sale.tenant, sale=sale, kind=kind,
            provider=provider, external_event_id=f"{kind}-{sale.pk}",
            amount_cents=sale.reported_total_cents,
            verification_digest="a" * 64,
            occurred_at=when, verified_at=timezone.now(),
        )

    def create_grant(self, ref, *, channel="vidalys_flow", minutes=10):
        sale = self.make_sale(ref, channel=channel)
        capture = self.proof(sale, minutes=minutes)
        grant, created = grant_for_captured_sale(
            sale_id=sale.pk, evidence_id=capture.pk, costs=self.costs,
        )
        self.assertTrue(created)
        return sale, grant, capture

    def change_sale(self, sale, status):
        serializer = OrderEventSerializer(data={
            "tenant_id": str(sale.tenant_id), "channel": sale.channel,
            "external_order_id": sale.external_reference,
            "customer_identifier": self.participant.contact_email,
            "total_amount": "100.00", "currency": "BRL",
            "status": status, "source_event_id": f"{status}-{sale.pk}",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        ingest_order_event(data=serializer.validated_data)
        sale.refresh_from_db()

    def test_untrusted_channel_paid_cannot_create_grant(self):
        sale = self.make_sale("NO-PROOF")
        self.assertEqual(sale_readiness(sale=sale), "requires_independent_capture")
        with self.assertRaises(FinancialEvidence.DoesNotExist):
            grant_for_captured_sale(
                sale_id=sale.pk, evidence_id="00000000-0000-0000-0000-000000000000",
                costs=self.costs,
            )
        self.assertFalse(LoyaltyGrant.objects.exists())
        self.assertFalse(PointEvent.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())

    def test_default_execution_gate_rejects_even_with_synthetic_evidence(self):
        sale = self.make_sale("BLOCKED")
        capture = self.proof(sale)
        with override_settings(FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=False):
            with self.assertRaises(PermissionError):
                grant_for_captured_sale(
                    sale_id=sale.pk, evidence_id=capture.pk, costs=self.costs,
                )
        self.assertFalse(LoyaltyGrant.objects.exists())

    def test_grant_is_atomic_idempotent_and_separate_ledgers(self):
        sale, grant, capture = self.create_grant("FLOW-101")
        again, created = grant_for_captured_sale(
            sale_id=sale.pk, evidence_id=capture.pk, costs=self.costs,
        )
        self.assertFalse(created)
        self.assertEqual(grant.pk, again.pk)
        self.assertEqual(grant.points_issued, 100)
        self.assertEqual(grant.cashback_cents, 500)
        self.assertEqual(grant.exposure_cents, 600)
        self.assertEqual(PointLot.objects.count(), 1)
        self.assertEqual(CashbackEvent.objects.count(), 1)
        self.assertEqual(LoyaltyGrant.objects.count(), 1)
        self.assertEqual(lot_balances(grant.point_lot)["pending"], 100)
        self.assertEqual(cashback_balances(grant.cashback_event.wallet)["pending_cents"], 500)
        self.assertEqual(MemberTierSnapshot.objects.get(participant=self.participant).tier, self.bronze)

    def test_release_after_hold_moves_both_ledgers_once(self):
        _, grant, _ = self.create_grant("RELEASE-100")
        first, changed = release_grant(grant_id=grant.pk)
        second, duplicate = release_grant(grant_id=grant.pk)
        self.assertTrue(changed)
        self.assertFalse(duplicate)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(lot_balances(grant.point_lot), {
            "pending": 0, "available": 100, "reserved": 0,
        })
        self.assertEqual(cashback_balances(grant.cashback_event.wallet), {
            "pending_cents": 0, "available_cents": 500, "reserved_cents": 0,
        })
        self.assertEqual(PointEvent.objects.count(), 2)
        self.assertEqual(CashbackEvent.objects.count(), 2)

    def test_second_purchase_multiplier_and_tier_progression(self):
        _, first, _ = self.create_grant("FIRST-100", minutes=60)
        _, second, _ = self.create_grant("SECOND-100", minutes=10)
        self.assertEqual(first.points_issued, 100)
        self.assertEqual(second.points_issued, 200)
        self.assertEqual(second.cashback_cents, 1000)
        snapshot = MemberTierSnapshot.objects.get(participant=self.participant)
        self.assertEqual(snapshot.tier, self.gold)
        self.assertEqual(snapshot.rolling_spend_cents, 20000)
        _, third, _ = self.create_grant("THIRD-100", minutes=2)
        self.assertEqual(third.points_issued, 150)
        self.assertEqual(third.cashback_cents, 750)

    def test_second_purchase_outside_window_has_no_multiplier(self):
        self.create_grant("FIRST-OLD", minutes=60 * 24 * 30)
        _, second, _ = self.create_grant("SECOND-NEW", minutes=10)
        self.assertEqual(second.points_issued, 100)

    def test_margin_and_budget_block_without_partial_credit(self):
        sale = self.make_sale("BAD-MARGIN")
        capture = self.proof(sale)
        self.cost.verified_at = None
        self.cost.save(update_fields=["verified_at"])
        with self.assertRaises(LoyaltyBlocked):
            grant_for_captured_sale(sale_id=sale.pk, evidence_id=capture.pk, costs=self.costs)
        self.assertFalse(PointLot.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())
        self.cost.verified_at = timezone.now()
        self.cost.save(update_fields=["verified_at"])
        self.rule.budget_cents = 100
        self.rule.save(update_fields=["budget_cents"])
        with self.assertRaises(LoyaltyBlocked):
            grant_for_captured_sale(sale_id=sale.pk, evidence_id=capture.pk, costs=self.costs)
        self.assertFalse(LoyaltyGrant.objects.exists())

    def test_invalid_provider_or_identity_blocks_grant(self):
        sale = self.make_sale("UNTRUSTED")
        proof = self.proof(sale, provider="self_reported")
        with self.assertRaises(LoyaltyBlocked):
            grant_for_captured_sale(sale_id=sale.pk, evidence_id=proof.pk, costs=self.costs)
        self.assertFalse(LoyaltyGrant.objects.exists())
        self.assertFalse(PointLot.objects.exists())

    def test_full_refund_reverses_pending_and_is_idempotent(self):
        sale, grant, _ = self.create_grant("REVERSE-PENDING")
        self.change_sale(sale, "refunded")
        refund = self.proof(sale, kind="refund", minutes=1)
        result, processed = reverse_grant(grant_id=grant.pk, refund_evidence_id=refund.pk)
        _, duplicate = reverse_grant(grant_id=grant.pk, refund_evidence_id=refund.pk)
        self.assertTrue(processed)
        self.assertFalse(duplicate)
        self.assertEqual(result.status, LoyaltyGrant.Status.REVERSED)
        self.assertEqual(lot_balances(grant.point_lot)["pending"], 0)
        self.assertEqual(cashback_balances(grant.cashback_event.wallet)["pending_cents"], 0)
        recovery = LoyaltyRecovery.objects.get(grant=grant)
        self.assertEqual(recovery.remaining_points, 0)
        self.assertEqual(recovery.remaining_cashback_cents, 0)
        self.assertIsNotNone(recovery.resolved_at)

    def test_full_refund_reverses_available_and_updates_tier(self):
        sale, grant, _ = self.create_grant("REVERSE-AVAILABLE")
        release_grant(grant_id=grant.pk)
        self.change_sale(sale, "cancelled")
        refund = self.proof(sale, kind="refund", minutes=1)
        reverse_grant(grant_id=grant.pk, refund_evidence_id=refund.pk)
        self.assertEqual(lot_balances(grant.point_lot)["available"], 0)
        self.assertEqual(cashback_balances(grant.cashback_event.wallet)["available_cents"], 0)
        self.assertEqual(MemberTierSnapshot.objects.get(participant=self.participant).rolling_spend_cents, 0)

    def test_points_voucher_reserve_and_single_use(self):
        _, grant, _ = self.create_grant("VOUCHER-PTS")
        release_grant(grant_id=grant.pk)
        voucher, code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(30, unit="points").pk,
        )
        self.assertTrue(verify_voucher(tenant_id=self.tenant.pk, code=code)["valid"])
        self.assertEqual(voucher.discount_cents, 30)
        self.assertEqual(lot_balances(grant.point_lot)["reserved"], 30)
        redeem_sale, redeem_proof = self.redemption_evidence("REDEEM-PTS-NEW")
        voucher, new = redeem_voucher(
            tenant_id=self.tenant.pk, code=code,
            channel="counter", external_receipt="Balcao-100",
            sale_id=redeem_sale.pk, capture_evidence_id=redeem_proof.pk,
        )
        same, again = redeem_voucher(
            tenant_id=self.tenant.pk, code=code,
            channel="counter", external_receipt="Balcao-100",
            sale_id=redeem_sale.pk, capture_evidence_id=redeem_proof.pk,
        )
        self.assertTrue(new)
        self.assertFalse(again)
        self.assertEqual(voucher.pk, same.pk)
        other_sale, other_evidence = self.redemption_evidence("REDEEM-OTHER-PROOF")
        with self.assertRaises(LoyaltyBlocked):
            redeem_voucher(
                tenant_id=self.tenant.pk, code=code, channel="counter",
                external_receipt="Balcao-100", sale_id=other_sale.pk,
                capture_evidence_id=other_evidence.pk,
            )
        self.assertEqual(lot_balances(grant.point_lot)["reserved"], 0)
        self.assertEqual(lot_balances(grant.point_lot)["available"], 70)
        self.assertEqual(VoucherPointAllocation.objects.count(), 1)
        with self.assertRaises(LoyaltyBlocked):
            redeem_voucher(
                tenant_id=self.tenant.pk, code=code,
                channel="counter", external_receipt="Balcao-200",
            sale_id=redeem_sale.pk, capture_evidence_id=redeem_proof.pk,
            )

    def test_cashback_voucher_can_be_cancelled_and_reserved_again(self):
        _, grant, _ = self.create_grant("VOUCHER-CASH")
        release_grant(grant_id=grant.pk)
        voucher, code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(200, unit="cashback").pk,
        )
        self.assertEqual(cashback_balances(grant.cashback_event.wallet)["reserved_cents"], 200)
        self.assertTrue(cancel_voucher(tenant_id=self.tenant.pk, voucher_id=voucher.pk))
        self.assertFalse(cancel_voucher(tenant_id=self.tenant.pk, voucher_id=voucher.pk))
        self.assertFalse(verify_voucher(tenant_id=self.tenant.pk, code=code)["valid"])
        self.assertEqual(cashback_balances(grant.cashback_event.wallet)["available_cents"], 500)

    def test_refund_after_redeemed_points_creates_explicit_recovery(self):
        sale, grant, _ = self.create_grant("REDEEM-THEN-REFUND")
        release_grant(grant_id=grant.pk)
        voucher, code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(30, unit="points").pk,
        )
        redeem_sale, redeem_proof = self.redemption_evidence("REDEEM-RECOVERY-NEW")
        redeem_voucher(
            tenant_id=self.tenant.pk, code=code,
            channel="counter", external_receipt="Applied-101",
            sale_id=redeem_sale.pk, capture_evidence_id=redeem_proof.pk,
        )
        self.change_sale(sale, "refunded")
        proof = self.proof(sale, kind="refund", minutes=1)
        reversed_grant, _ = reverse_grant(grant_id=grant.pk, refund_evidence_id=proof.pk)
        self.assertEqual(reversed_grant.status, LoyaltyGrant.Status.RECOVERY)
        recovery = LoyaltyRecovery.objects.get(grant=grant)
        self.assertEqual(recovery.remaining_points, 30)
        self.assertEqual(recovery.remaining_cashback_cents, 0)
        self.assertEqual(lot_balances(grant.point_lot)["available"], 0)
        with self.assertRaises(LoyaltyBlocked):
            issue_voucher(
                tenant_id=self.tenant.pk, participant_id=self.participant.pk,
                reward_id=self.reward(1, unit="points").pk,
            )

    def test_grant_does_not_depend_on_nuvemshop(self):
        _, grant, _ = self.create_grant("COUNTER-100", channel="counter")
        self.assertEqual(grant.sale.channel, SaleRecord.Channel.COUNTER)
        self.assertEqual(grant.points_issued, 100)
        self.assertFalse(self.tenant.nuvemshop_installation_id if hasattr(
            self.tenant, "nuvemshop_installation_id"
        ) else False)


    def test_cancelled_order_cannot_release_before_verified_refund(self):
        sale, grant, _ = self.create_grant("CANCEL-BEFORE-RELEASE")
        self.change_sale(sale, "cancelled")
        with self.assertRaises(LoyaltyBlocked):
            release_grant(grant_id=grant.pk)
        self.assertEqual(lot_balances(grant.point_lot)["pending"], 100)
        self.assertEqual(cashback_balances(grant.cashback_event.wallet)["pending_cents"], 500)

    def test_refund_cancels_reserved_vouchers_before_reversing(self):
        sale, grant, _ = self.create_grant("REFUND-RESERVED")
        release_grant(grant_id=grant.pk)
        voucher, code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(80, unit="points").pk,
        )
        cashback_voucher, cash_code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(200, unit="cashback").pk,
        )
        self.change_sale(sale, "refunded")
        proof = self.proof(sale, kind="refund", minutes=1)
        result, changed = reverse_grant(grant_id=grant.pk, refund_evidence_id=proof.pk)
        self.assertTrue(changed)
        self.assertEqual(result.status, LoyaltyGrant.Status.REVERSED)
        voucher.refresh_from_db()
        cashback_voucher.refresh_from_db()
        self.assertEqual(voucher.state, LoyaltyVoucher.State.CANCELLED)
        self.assertEqual(cashback_voucher.state, LoyaltyVoucher.State.CANCELLED)
        self.assertFalse(verify_voucher(tenant_id=self.tenant.pk, code=code)["valid"])
        self.assertFalse(verify_voucher(tenant_id=self.tenant.pk, code=cash_code)["valid"])
        self.assertEqual(lot_balances(grant.point_lot)["reserved"], 0)
        self.assertEqual(cashback_balances(grant.cashback_event.wallet)["reserved_cents"], 0)
        self.assertEqual(lot_balances(grant.point_lot)["available"], 0)

    def test_cross_tenant_financial_proof_rejected(self):
        sale = self.make_sale("CROSS-TENANT")
        # Um comprovante criado já com tenant incorreto deve ser rejeitado.
        # Depois do PR26, UPDATE no PostgreSQL é bloqueado por trigger.
        capture = FinancialEvidence.objects.create(
            tenant=self.another_tenant, sale=sale,
            kind=FinancialEvidence.Kind.CAPTURE,
            provider="psp_test", external_event_id="cross-tenant-test",
            amount_cents=sale.reported_total_cents,
            verification_digest="a"*64,
            occurred_at=timezone.now()-timedelta(minutes=10),
            verified_at=timezone.now(),
        )
        with self.assertRaises(LoyaltyBlocked):
            grant_for_captured_sale(sale_id=sale.pk, evidence_id=capture.pk, costs=self.costs)
        self.assertFalse(LoyaltyGrant.objects.exists())

    def test_duplicate_receipt_cannot_redeem_different_voucher(self):
        _, grant, _ = self.create_grant("TWO-VOUCHERS")
        release_grant(grant_id=grant.pk)
        one, code1 = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(10, unit="points").pk,
        )
        two, code2 = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(10, unit="points").pk,
        )
        redeem_sale, redeem_proof = self.redemption_evidence("REDEEM-SAME-NEW")
        redeem_voucher(
            tenant_id=self.tenant.pk, code=code1,
            channel="counter", external_receipt="same-0001",
            sale_id=redeem_sale.pk, capture_evidence_id=redeem_proof.pk,
        )
        with self.assertRaises(LoyaltyBlocked):
            redeem_voucher(
                tenant_id=self.tenant.pk, code=code2,
                channel="counter", external_receipt="same-0001",
            sale_id=redeem_sale.pk, capture_evidence_id=redeem_proof.pk,
            )
        two.refresh_from_db()
        self.assertEqual(two.state, LoyaltyVoucher.State.RESERVED)
        self.assertEqual(lot_balances(grant.point_lot)["reserved"], 10)

    def test_voucher_isolation_by_tenant_and_no_plaintext_in_database(self):
        _, grant, _ = self.create_grant("PRIVATE-VOUCHER")
        release_grant(grant_id=grant.pk)
        voucher, code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(100, unit="cashback").pk,
        )
        self.assertEqual(len(code), 26)
        self.assertNotEqual(voucher.code_digest, code)
        self.assertEqual(len(voucher.code_digest), 64)
        self.assertFalse(verify_voucher(tenant_id=self.another_tenant.pk, code=code)["valid"])
        with self.assertRaises(LoyaltyBlocked):
            redeem_voucher(
                tenant_id=self.another_tenant.pk, code=code,
                channel="counter", external_receipt="foreign-222",
                sale_id=grant.sale_id, capture_evidence_id=grant.evidence_id,
            )

    def test_refund_never_debits_cashback_from_another_purchase(self):
        """P0: spent credit of grant A must not consume available credit of B."""
        first_sale, first, _ = self.create_grant("ORIGIN-A", minutes=12)
        _, second, _ = self.create_grant("ORIGIN-B", minutes=11)
        release_grant(grant_id=first.pk)
        release_grant(grant_id=second.pk)
        second_available = origin_balances(second.cashback_event)["available_cents"]
        voucher, code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(300, unit="cashback").pk,
        )
        redeem_sale, redeem_proof = self.redemption_evidence("ORIGIN-REDEEM")
        redeem_voucher(
            tenant_id=self.tenant.pk, code=code,
            channel="counter", external_receipt="ORIGIN-RECEIPT",
            sale_id=redeem_sale.pk, capture_evidence_id=redeem_proof.pk,
        )
        self.change_sale(first_sale, "refunded")
        refund = self.proof(first_sale, kind="refund", minutes=1)
        reversed_grant, _ = reverse_grant(grant_id=first.pk, refund_evidence_id=refund.pk)
        self.assertEqual(reversed_grant.status, LoyaltyGrant.Status.RECOVERY)
        self.assertEqual(origin_balances(second.cashback_event)["available_cents"], second_available)
        self.assertEqual(LoyaltyRecovery.objects.get(grant=first).remaining_cashback_cents, 300)
        self.assertEqual(origin_balances(first.cashback_event)["available_cents"], 0)
        self.assertEqual(cashback_balances(second.cashback_event.wallet)["available_cents"], second_available)

    def test_refund_of_other_grant_preserves_redeemed_purchase_origin(self):
        """Two purchases, redeem A, refund B: A's remaining credit is unchanged."""
        _, first, _ = self.create_grant("REDEEM-FIRST-A", minutes=12)
        second_sale, second, _ = self.create_grant("REFUND-SECOND-B", minutes=11)
        release_grant(grant_id=first.pk)
        release_grant(grant_id=second.pk)
        voucher, code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=self.reward(100, unit="cashback").pk,
        )
        redeem_sale, proof = self.redemption_evidence("REDEEM-FIRST-CHECKOUT")
        redeem_voucher(
            tenant_id=self.tenant.pk, code=code, channel="counter",
            external_receipt="REDEEM-FIRST-CHECKOUT",
            sale_id=redeem_sale.pk, capture_evidence_id=proof.pk,
        )
        before = origin_balances(first.cashback_event)
        self.assertEqual(before["available_cents"], first.cashback_cents - 100)
        self.change_sale(second_sale, "refunded")
        refund = self.proof(second_sale, kind="refund", minutes=1)
        reversed_grant, changed = reverse_grant(
            grant_id=second.pk, refund_evidence_id=refund.pk,
        )
        self.assertTrue(changed)
        self.assertEqual(reversed_grant.status, LoyaltyGrant.Status.REVERSED)
        self.assertEqual(origin_balances(first.cashback_event), before)
        self.assertEqual(origin_balances(second.cashback_event)["available_cents"], 0)
        self.assertEqual(LoyaltyRecovery.objects.get(grant=second).remaining_cashback_cents, 0)

    def test_voucher_requires_published_reward_and_enforces_quota(self):
        _, grant, _ = self.create_grant("REWARD-PUBLICATION")
        release_grant(grant_id=grant.pk)
        reward = self.reward(10, max_redemptions=1)
        reward.publication_status = DiscountRewardDraft.PublicationStatus.DRAFT
        reward.save(update_fields=["publication_status"])
        with self.assertRaises(LoyaltyBlocked):
            issue_voucher(
                tenant_id=self.tenant.pk, participant_id=self.participant.pk,
                reward_id=reward.pk,
            )
        reward.publication_status = DiscountRewardDraft.PublicationStatus.PUBLISHED
        reward.save(update_fields=["publication_status"])
        issue_voucher(tenant_id=self.tenant.pk, participant_id=self.participant.pk, reward_id=reward.pk)
        with self.assertRaises(LoyaltyBlocked):
            issue_voucher(
                tenant_id=self.tenant.pk, participant_id=self.participant.pk,
                reward_id=reward.pk,
            )

    def test_voucher_minimum_order_and_channel_are_verified_at_redemption(self):
        _, grant, _ = self.create_grant("REWARD-MINIMUM")
        release_grant(grant_id=grant.pk)
        reward = self.reward(10)
        reward.min_order_cents = 12000
        reward.allowed_channels = "counter"
        reward.save(update_fields=["min_order_cents", "allowed_channels"])
        _, code = issue_voucher(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            reward_id=reward.pk,
        )
        redeem_sale, redeem_proof = self.redemption_evidence("REWARD-LOW-ORDER")
        with self.assertRaises(LoyaltyBlocked):
            redeem_voucher(
                tenant_id=self.tenant.pk, code=code, channel="counter",
                external_receipt="LOW-ORDER-100",
                sale_id=redeem_sale.pk, capture_evidence_id=redeem_proof.pk,
            )
        with self.assertRaises(LoyaltyBlocked):
            redeem_voucher(
                tenant_id=self.tenant.pk, code=code, channel="vidalys_flow",
                external_receipt="WRONG-CHANNEL-100",
                sale_id=redeem_sale.pk, capture_evidence_id=redeem_proof.pk,
            )

    def test_profile_birthday_mission_requires_verified_contact_and_consent(self):
        with self.assertRaises(LoyaltyBlocked):
            record_engagement_eligibility(
                participant_id=self.participant.pk, kind=LoyaltyEngagement.Kind.PROFILE,
            )
        attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            phone_e164="+5531999999999", proof_method="whatsapp_otp",
        )
        today = timezone.now()
        profile = CustomerProfile.objects.get(pk=self.profile.pk)
        profile.birth_date = today.date().replace(year=2001)
        profile.birth_date_consent_at = today - timedelta(days=1)
        profile.birth_date_verified_at = today - timedelta(hours=3)
        profile.save(update_fields=[
            "birth_date", "birth_date_consent_at", "birth_date_verified_at",
        ])
        first, created = record_engagement_eligibility(
            participant_id=self.participant.pk, kind=LoyaltyEngagement.Kind.PROFILE,
        )
        _, again = record_engagement_eligibility(
            participant_id=self.participant.pk, kind=LoyaltyEngagement.Kind.PROFILE,
        )
        self.assertTrue(created)
        self.assertFalse(again)
        birthday, once = record_engagement_eligibility(
            participant_id=self.participant.pk, kind=LoyaltyEngagement.Kind.BIRTHDAY,
        )
        _, duplicate = record_engagement_eligibility(
            participant_id=self.participant.pk, kind=LoyaltyEngagement.Kind.BIRTHDAY,
        )
        self.assertTrue(once)
        self.assertFalse(duplicate)
        self.assertNotEqual(first.pk, birthday.pk)
        self.assertFalse(PointEvent.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())

    def test_winback_task_only_records_eligibility_and_is_idempotent(self):
        self.rule.winback_after_days = 45
        self.rule.save(update_fields=["winback_after_days"])
        self.create_grant("WINBACK-FIRST", minutes=60 * 24 * 50)
        with override_settings(FIDELIZA_LOYALTY_ENGAGEMENT_SCAN_ENABLED=True):
            first = scan_winback()
            second = scan_winback()
        self.assertFalse(first["skipped"])
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(LoyaltyEngagement.objects.count(), 1)
        self.assertEqual(LoyaltyEngagement.objects.get().kind, LoyaltyEngagement.Kind.WINBACK)
        self.assertEqual(first["notifications_sent"], 0)
        self.assertEqual(PointEvent.objects.count(), 1)
        self.assertEqual(CashbackEvent.objects.count(), 1)

    def test_release_task_skips_when_gate_closed(self):
        _, grant, _ = self.create_grant("TASK-RELEASE")
        with override_settings(FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=False):
            skipped = release_due_grants()
        self.assertTrue(skipped["skipped"])
        self.assertEqual(lot_balances(grant.point_lot)["pending"], 100)
        processed = release_due_grants()
        self.assertEqual(processed["released"], 1)
        self.assertEqual(lot_balances(grant.point_lot)["available"], 100)

    def test_voucher_endpoints_are_closed_by_default(self):
        user = get_user_model().objects.create_user(username="pr20-operator")
        from apps.tenants.models import TenantMembership
        TenantMembership.objects.create(
            tenant=self.tenant, user=user, role=TenantMembership.Role.OWNER,
        )
        api = APIClient()
        api.force_login(user)
        route = reverse("loyalty-voucher-check", kwargs={"tenant_id": self.tenant.pk})
        with override_settings(FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=False):
            response = api.post(route, {"code": "VF" + "A" * 24}, format="json")
        self.assertEqual(response.status_code, 409)

    def test_calculation_is_pure_and_never_writes_ledger(self):
        quote = calculate_reward(
            rule=self.rule, eligible_cents=10000, tier=self.bronze,
            prior_count=1, days_since_first=2,
        )
        self.assertEqual(quote.points, 200)
        self.assertEqual(quote.cashback_cents, 1000)
        self.assertTrue(quote.second_purchase)
        self.assertFalse(PointEvent.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())


    def test_rule_and_tier_cannot_be_rewritten_after_payout(self):
        self.create_grant("IMMUTABLE-RULE")
        self.rule.cashback_bps = 9500
        with self.assertRaises(ValueError):
            self.rule.save(update_fields=["cashback_bps"])
        self.gold.multiplier_bps = 30000
        with self.assertRaises(ValueError):
            self.gold.save(update_fields=["multiplier_bps"])
        self.assertEqual(LoyaltyRule.objects.get(pk=self.rule.pk).cashback_bps, 500)

    def test_refund_evidence_cannot_be_changed_or_deleted(self):
        sale = self.make_sale("IMMUTABLE-EVIDENCE")
        evidence = self.proof(sale)
        evidence.amount_cents = 1
        with self.assertRaises(ValueError):
            evidence.save()
        with self.assertRaises(ValueError):
            evidence.delete()


    def test_refund_worker_requires_psp_proof_not_only_status(self):
        sale, grant, _ = self.create_grant("PSP-REFUND-TASK")
        self.change_sale(sale, "refunded")
        result = reconcile_verified_refunds()
        self.assertEqual(result["reversed"], 0)
        self.assertEqual(result["pending_review"], 1)
        self.assertEqual(LoyaltyGrant.objects.get(pk=grant.pk).status,
                         LoyaltyGrant.Status.PENDING)
        self.assertEqual(lot_balances(grant.point_lot)["pending"], 100)
        self.proof(sale, kind="refund", minutes=1)
        processed = reconcile_verified_refunds()
        self.assertEqual(processed["reversed"], 1)
        grant.refresh_from_db()
        self.assertEqual(grant.status, LoyaltyGrant.Status.REVERSED)
        self.assertEqual(lot_balances(grant.point_lot)["pending"], 0)
        self.assertEqual(reconcile_verified_refunds()["reversed"], 0)

    def test_refund_worker_is_disabled_in_runtime_default(self):
        with override_settings(FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED=False):
            result = reconcile_verified_refunds()
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reversed"], 0)


    def test_birthday_task_requires_verified_birthdate_and_opt_in(self):
        now = timezone.now()
        profile = CustomerProfile.objects.get(pk=self.profile.pk)
        profile.birth_date = now.date().replace(year=2001)
        profile.birth_date_verified_at = now
        profile.birth_date_consent_at = now
        profile.save(update_fields=[
            "birth_date", "birth_date_verified_at", "birth_date_consent_at",
        ])
        with override_settings(FIDELIZA_LOYALTY_ENGAGEMENT_SCAN_ENABLED=True):
            without_phone = scan_verified_birthdays()
        self.assertEqual(without_phone["created"], 0)
        attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=self.participant.pk,
            phone_e164="+5531999999999", proof_method="whatsapp_otp",
        )
        with override_settings(FIDELIZA_LOYALTY_ENGAGEMENT_SCAN_ENABLED=True):
            first = scan_verified_birthdays()
            second = scan_verified_birthdays()
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(LoyaltyEngagement.objects.count(), 1)
        self.assertEqual(first["notifications_sent"], 0)
        self.assertFalse(PointEvent.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())


    def test_birthdate_cannot_be_stored_without_consent(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CustomerProfile.objects.filter(pk=self.profile.pk).update(
                    birth_date=timezone.now().date(), birth_date_consent_at=None,
                )
        self.assertIsNone(CustomerProfile.objects.get(pk=self.profile.pk).birth_date)


    def test_paid_transition_returns_actionable_readiness_without_credit(self):
        from rest_framework.test import APIClient
        from apps.channels.services import issue_flow_key
        from apps.tenants.models import TenantMembership
        user = get_user_model().objects.create_user(username="pr20-flow-owner")
        TenantMembership.objects.create(
            tenant=self.tenant, user=user, role=TenantMembership.Role.OWNER,
        )
        _, token = issue_flow_key(
            tenant_id=self.tenant.pk, label="Test read-only readiness", actor=user,
        )
        response = APIClient().post(
            reverse("channel-order-events"),
            {
                "tenant_id": str(self.tenant.pk), "channel": "vidalys_flow",
                "external_order_id": "READINESS-100",
                "customer_identifier": self.participant.contact_email,
                "total_amount": "100.00", "currency": "BRL",
                "status": "paid", "source_event_id": "readiness-evt-1",
            }, format="json", HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["loyalty_readiness"], "requires_independent_capture")
        self.assertFalse(response.data["points_credited"])
        self.assertFalse(PointLot.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())
