"""Testes sintéticos: não representam pedidos ou saldos reais."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.participants.models import ProgramParticipant
from apps.tenants.models import Tenant, TenantMembership
from .models import CashbackEntry, CashbackEvent, CashbackWallet
from .services import append_cashback_event, wallet_balances


class LedgerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="wallet-owner")
        self.tenant = Tenant.objects.create(name="Loja QA", slug="wallet-qa")
        self.other_tenant = Tenant.objects.create(name="Outra QA", slug="wallet-other")
        TenantMembership.objects.create(tenant=self.tenant, user=self.user, role="owner")
        self.participant = ProgramParticipant.objects.create(
            tenant=self.tenant, external_customer_id="cust-1",
            consent_at=timezone.now() - timedelta(days=1),
            consent_channel="customer_portal", terms_version="v1",
        )
        self.client = APIClient()

    def path(self, tenant=None, participant=None):
        return reverse("participant-wallet", kwargs={
            "tenant_id": tenant or self.tenant.pk,
            "participant_id": participant or self.participant.pk,
        })

    def post_event(self, kind, amount, key, order="order-1", participant=None):
        return append_cashback_event(
            participant=participant or self.participant,
            kind=kind, amount_cents=amount, idempotency_key=key,
            source_order_id=order, rule_version="rule-1",
        )

    def test_writes_disabled_by_default(self):
        with self.assertRaises(PermissionError):
            self.post_event("accrual", 400, "order-paid-1")
        self.assertEqual(CashbackEvent.objects.count(), 0)
        self.assertEqual(CashbackWallet.objects.count(), 0)

    @override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=True)
    def test_ledger_lifecycle_and_idempotency(self):
        event, created = self.post_event("accrual", 400, "paid-1")
        self.assertTrue(created)
        duplicate, created = self.post_event("accrual", 400, "paid-1")
        self.assertFalse(created)
        self.assertEqual(duplicate.pk, event.pk)
        with self.assertRaisesRegex(ValueError, "reutilizada"):
            self.post_event("accrual", 500, "paid-1")
        self.assertEqual(CashbackEvent.objects.count(), 1)

        self.post_event("release", 400, "release-1")
        wallet = CashbackWallet.objects.get(participant=self.participant)
        self.assertEqual(wallet_balances(wallet), {
            "pending_cents": 0, "available_cents": 400, "reserved_cents": 0,
        })
        with self.assertRaisesRegex(ValueError, "insuficiente"):
            self.post_event("reserve", 401, "reserve-too-much")
        self.post_event("reserve", 250, "reserve-1")
        self.post_event("redeem", 250, "redeem-1")
        self.post_event("expire", 150, "expire-1")
        self.assertEqual(wallet_balances(wallet), {
            "pending_cents": 0, "available_cents": 0, "reserved_cents": 0,
        })
        self.assertEqual(CashbackEvent.objects.count(), 5)
        self.assertEqual(CashbackEntry.objects.count(), 7)

    @override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=True)
    def test_insufficient_and_cancel_reservation(self):
        with self.assertRaisesRegex(ValueError, "insuficiente"):
            self.post_event("release", 300, "bad-release")
        self.post_event("accrual", 100, "paid-1")
        self.post_event("release", 100, "release-1")
        self.post_event("reserve", 75, "reserve-1")
        self.post_event("cancel_reservation", 75, "cancel-reserve-1")
        self.assertEqual(wallet_balances(CashbackWallet.objects.get()), {
            "pending_cents": 0, "available_cents": 100, "reserved_cents": 0,
        })

    @override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=True)
    def test_invalid_events_and_withdrawn_no_accrual(self):
        for value in (0, -1, 100_000_001, "200", True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.post_event("accrual", value, "bad-amount")
        with self.assertRaises(ValueError):
            self.post_event("unknown", 100, "event-1")
        with self.assertRaises(ValueError):
            self.post_event("accrual", 100, "not-ascii-ç")
        self.participant.status = ProgramParticipant.Status.WITHDRAWN
        self.participant.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            self.post_event("accrual", 100, "paid-2")

    @override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=True)
    def test_ledger_events_cannot_be_changed_via_model_instance(self):
        event, _ = self.post_event("accrual", 110, "paid-1")
        with self.assertRaises(ValueError):
            event.delete()
        with self.assertRaises(ValueError):
            event.save()
        entry = event.entries.first()
        with self.assertRaises(ValueError):
            entry.delete()
        with self.assertRaises(ValueError):
            entry.save()

    def test_read_only_requires_membership_and_does_not_fabricate_zero(self):
        self.assertIn(self.client.get(self.path()).status_code, (401, 403))
        self.client.force_authenticate(self.user)
        result = self.client.get(self.path())
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.data["balances"])
        self.assertEqual(result.data["balance_status"], "not_implemented")
        self.assertFalse(result.data["redemption_enabled"])
        self.assertEqual(result["Cache-Control"], "private, no-store")
        self.assertEqual(self.client.post(self.path(), {"amount": 100}).status_code, 405)
        self.assertEqual(self.client.patch(self.path(), {"amount": 100}).status_code, 405)
        self.assertEqual(self.client.get(self.path(tenant=self.other_tenant.pk)).status_code, 404)

    @override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=True)
    def test_private_history_contains_only_selected_tenant(self):
        self.post_event("accrual", 200, "paid-1")
        self.client.force_authenticate(self.user)
        result = self.client.get(self.path())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["balances"]["pending_cents"], 200)
        self.assertEqual(result.data["balance_status"], "ledger_only")
        self.assertEqual(len(result.data["events"]), 1)
        self.assertEqual(result.data["events"][0]["kind"], "accrual")
        self.assertNotIn("idempotency_key", str(result.data))
        self.assertNotIn("source_order_id", str(result.data))
        members = self.client.get(reverse("tenant-participants", kwargs={
            "tenant_id": self.tenant.pk,
        }))
        self.assertEqual(members.status_code, 200)
        self.assertEqual(members.data["items"][0]["cashback_pending_cents"], 200)
        self.assertEqual(members.data["items"][0]["cashback_balance_cents"], 0)
        self.assertEqual(members.data["items"][0]["balance_status"], "ledger_only")

        self.participant.status = ProgramParticipant.Status.WITHDRAWN
        self.participant.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.path()).status_code, 404)
        self.assertEqual(self.client.get(reverse("tenant-participants", kwargs={
            "tenant_id": self.tenant.pk,
        })).data["summary"]["total"], 0)
