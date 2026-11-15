"""Read-only member dashboard must not create VIP or currency totals."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.loyalty.models import FinancialEvidence, LoyaltyGrant, LoyaltyRule, LoyaltyTier
from apps.participants.member_portal_views import (
    _member_cashback_snapshot, _member_missions, _member_vip_snapshot,
)
from apps.participants.models import ProgramParticipant
from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant
from apps.wallets.models import CashbackEvent
from apps.wallets.services import append_cashback_event


class ClubReadOnlyDashboardTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja Fidelidade", slug="clube-readonly", status=Tenant.Status.ACTIVE,
        )
        self.other = Tenant.objects.create(
            name="Outra Loja", slug="clube-readonly-other", status=Tenant.Status.ACTIVE,
        )
        self.participant = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Cliente QA", contact_email="cliente@example.com",
            status=ProgramParticipant.Status.ACTIVE,
            consent_at=timezone.now() - timedelta(days=45),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1",
        )

    def test_missing_rule_and_wallet_are_unavailable_not_fake_zero(self):
        self.assertEqual(_member_vip_snapshot(self.tenant, self.participant), {
            "vip_level": None, "vip_next_level": None, "vip_progress_percent": None,
        })
        self.assertEqual(_member_cashback_snapshot(self.tenant, self.participant), {
            "cashback_balance_cents": None,
            "cashback_pending_cents": None,
            "cashback_status": "not_active",
        })
        self.assertEqual(_member_missions(self.tenant, self.participant), [])

    def test_tier_reads_only_grants_from_same_tenant_and_rolling_window(self):
        rule = LoyaltyRule.objects.create(
            tenant=self.tenant, version=1, enabled=True, budget_cents=100000,
        )
        bronze = LoyaltyTier.objects.create(
            rule=rule, name="Bronze", minimum_spend_cents=0, multiplier_bps=10000,
        )
        silver = LoyaltyTier.objects.create(
            rule=rule, name="Prata", minimum_spend_cents=10000, multiplier_bps=12000,
        )
        gold = LoyaltyTier.objects.create(
            rule=rule, name="Ouro", minimum_spend_cents=20000, multiplier_bps=15000,
        )
        empty = _member_vip_snapshot(self.tenant, self.participant)
        self.assertEqual(empty["vip_level"], bronze.name)
        self.assertEqual(empty["vip_progress_percent"], 0)

        when = timezone.now() - timedelta(days=1)
        sale = SaleRecord.objects.create(
            tenant=self.tenant, channel="counter", external_reference="VIP-READONLY-100",
            eligible_amount_cents=0, reported_total_cents=12000,
            currency="BRL", order_status="paid", status_changed_at=when,
            state=SaleRecord.State.AWAITING_MEMBER,
        )
        evidence = FinancialEvidence.objects.create(
            tenant=self.tenant, sale=sale, kind=FinancialEvidence.Kind.CAPTURE,
            provider="psp_test", external_event_id="snapshot-readonly",
            amount_cents=12000, verification_digest="a" * 64,
            occurred_at=when, verified_at=timezone.now(),
        )
        LoyaltyGrant.objects.create(
            tenant=self.tenant, sale=sale, participant=self.participant,
            rule=rule, evidence=evidence,
            eligible_amount_cents=12000, points_issued=0, cashback_cents=0,
            exposure_cents=0, captured_at=when, unlock_at=when,
            expires_at=timezone.now() + timedelta(days=180),
            status=LoyaltyGrant.Status.RELEASED,
        )
        current = _member_vip_snapshot(self.tenant, self.participant)
        self.assertEqual(current["vip_level"], silver.name)
        self.assertEqual(current["vip_next_level"], gold.name)
        self.assertEqual(current["vip_progress_percent"], 20)
        self.assertIsNone(_member_vip_snapshot(self.other, self.participant)["vip_level"])

    @override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=True)
    def test_cashback_is_derived_only_from_immutable_ledger(self):
        append_cashback_event(
            participant=self.participant, kind=CashbackEvent.Kind.ACCRUAL,
            amount_cents=345, idempotency_key="snapshot:accrual",
            rule_version="v1", source_order_id="VIP-100",
        )
        pending = _member_cashback_snapshot(self.tenant, self.participant)
        self.assertEqual(pending["cashback_pending_cents"], 345)
        self.assertEqual(pending["cashback_balance_cents"], 0)
        append_cashback_event(
            participant=self.participant, kind=CashbackEvent.Kind.RELEASE,
            amount_cents=345, idempotency_key="snapshot:release",
            rule_version="v1", source_order_id="VIP-100",
        )
        result = _member_cashback_snapshot(self.tenant, self.participant)
        self.assertEqual(result["cashback_balance_cents"], 345)
        self.assertEqual(result["cashback_pending_cents"], 0)
        self.assertEqual(result["cashback_status"], "ledger_only")
        self.assertIsNone(_member_cashback_snapshot(self.other, self.participant)["cashback_balance_cents"])
