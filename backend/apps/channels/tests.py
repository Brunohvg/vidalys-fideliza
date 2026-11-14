"""PR19: eventos multi-tenant sem escrituração financeira."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.customers.models import (
    ChannelCustomerReference, CustomerProfile, VerifiedCustomerContact,
)
from apps.customers.services import attach_verified_contact
from apps.nuvemshop.models import NuvemshopInstallation
from apps.participants.models import ProgramParticipant
from apps.points.models import PointEntry, PointEvent, PointWallet
from apps.sales.models import SaleEventReceipt, SaleRecord
from apps.tenants.models import Tenant, TenantMembership
from apps.wallets.models import CashbackEntry, CashbackEvent, CashbackWallet

from .adapters.nuvemshop import NuvemshopSnapshotError, ingest_nuvemshop_snapshot
from .models import ChannelCredential
from .serializers import OrderEventSerializer
from .services import (
    IngestionConflict, authenticate_flow_key, ingest_order_event, issue_flow_key,
)


@override_settings(
    FIDELIZA_POINTS_WRITES_ENABLED=False,
    FIDELIZA_LEDGER_WRITES_ENABLED=False,
)
class MultiChannelOrderTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            slug="pr19-store", name="Loja independente", status=Tenant.Status.ACTIVE,
        )
        self.other = Tenant.objects.create(
            slug="pr19-other", name="Outra loja", status=Tenant.Status.ACTIVE,
        )
        User = get_user_model()
        self.owner = User.objects.create_user(username="pr19-owner")
        self.analyst = User.objects.create_user(username="pr19-analyst")
        TenantMembership.objects.create(
            tenant=self.tenant, user=self.owner, role=TenantMembership.Role.OWNER,
        )
        TenantMembership.objects.create(
            tenant=self.tenant, user=self.analyst, role=TenantMembership.Role.ANALYST,
        )
        TenantMembership.objects.create(
            tenant=self.other, user=self.owner, role=TenantMembership.Role.OWNER,
        )
        _, self.key = issue_flow_key(
            tenant_id=self.tenant.id, label="Flow piloto", actor=self.owner,
        )
        _, self.other_key = issue_flow_key(tenant_id=self.other.id, label="Flow B", actor=self.owner)
        self.client = APIClient()
        self.url = reverse("channel-order-events")

    def payload(self, *, tenant=None, channel="vidalys_flow", order="FLOW-100", **overrides):
        data = {
            "tenant_id": str(tenant or self.tenant.pk),
            "channel": channel,
            "external_order_id": order,
            "customer_identifier": "+5531999999999",
            "total_amount": "149.90",
            "currency": "BRL",
            "status": "pending",
            "source_event_id": "evt-100",
        }
        data.update(overrides)
        return data

    def flow(self, data, key=None):
        return self.client.post(
            self.url, data, format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.key if key is None else key}",
        )

    def assert_no_financial_writes(self):
        self.assertFalse(PointWallet.objects.exists())
        self.assertFalse(PointEvent.objects.exists())
        self.assertFalse(PointEntry.objects.exists())
        self.assertFalse(CashbackWallet.objects.exists())
        self.assertFalse(CashbackEvent.objects.exists())
        self.assertFalse(CashbackEntry.objects.exists())

    def test_flow_intake_creates_provisional_profile_but_no_verified_contact_or_credit(self):
        response = self.flow(self.payload())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["created"])
        self.assertFalse(response.data["payment_verified"])
        self.assertFalse(response.data["points_credited"])
        self.assertEqual(response.data["identity_status"], "provisional")
        sale = SaleRecord.objects.get()
        self.assertIsNone(sale.participant_id)
        self.assertIsNotNone(sale.customer_profile_id)
        self.assertEqual(sale.eligible_amount_cents, 0)
        self.assertEqual(sale.reported_total_cents, 14990)
        self.assertEqual(sale.order_status, "pending")
        self.assertFalse(VerifiedCustomerContact.objects.exists())
        self.assert_no_financial_writes()

    def test_exact_retry_is_idempotent_even_when_webhook_repeats(self):
        request = self.payload()
        first = self.flow(request)
        second = self.flow(request)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["duplicate"])
        self.assertEqual(first.data["sale_id"], second.data["sale_id"])
        self.assertEqual(first.data["event_id"], second.data["event_id"])
        self.assertEqual(SaleRecord.objects.count(), 1)
        self.assertEqual(SaleEventReceipt.objects.count(), 1)
        self.assertEqual(CustomerProfile.objects.count(), 1)
        self.assert_no_financial_writes()

    def test_status_changes_preserve_one_order_and_immutable_events(self):
        self.assertEqual(self.flow(self.payload()).status_code, 201)
        paid = self.flow(self.payload(status="paid", source_event_id="evt-101"))
        refund = self.flow(self.payload(status="refunded", source_event_id="evt-102"))
        stale = self.flow(self.payload(status="pending", source_event_id="evt-103"))
        self.assertEqual([paid.status_code, refund.status_code, stale.status_code],
                         [200, 200, 200])
        self.assertEqual(stale.data["event_outcome"], SaleEventReceipt.Outcome.IGNORED)
        self.assertEqual(SaleRecord.objects.count(), 1)
        self.assertEqual(SaleRecord.objects.get().order_status, "refunded")
        self.assertEqual(SaleEventReceipt.objects.count(), 4)
        self.assert_no_financial_writes()

    def test_event_id_reused_with_different_payload_is_conflict(self):
        self.flow(self.payload())
        wrong_status = self.flow(self.payload(status="paid"))
        wrong_amount = self.flow(self.payload(total_amount="150.90"))
        self.assertEqual(wrong_status.status_code, 409)
        self.assertEqual(wrong_amount.status_code, 409)
        self.assertEqual(SaleEventReceipt.objects.count(), 1)
        self.assertEqual(SaleRecord.objects.get().order_status, "pending")

    def test_event_id_reused_on_another_order_is_conflict(self):
        self.flow(self.payload())
        second = self.flow(self.payload(order="FLOW-200"))
        self.assertEqual(second.status_code, 409)
        self.assertEqual(SaleRecord.objects.count(), 1)

    def test_same_external_id_for_other_tenant_is_isolated(self):
        self.assertEqual(self.flow(self.payload()).status_code, 201)
        blocked = self.flow(self.payload(tenant=self.other.pk))
        self.assertEqual(blocked.status_code, 401)
        accepted = self.flow(self.payload(tenant=self.other.pk), key=self.other_key)
        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(SaleRecord.objects.count(), 2)
        self.assertNotEqual(*list(SaleRecord.objects.order_by("id").values_list(
            "tenant_id", flat=True
        )))
        self.assert_no_financial_writes()

    def test_only_tenant_administrator_can_issue_flow_key(self):
        with self.assertRaises(PermissionError):
            issue_flow_key(
                tenant_id=self.tenant.pk, label="Invasor", actor=self.analyst,
            )
        with self.assertRaises(PermissionError):
            issue_flow_key(
                tenant_id=self.tenant.pk, label="Sem login", actor=None,
            )
        self.assertEqual(ChannelCredential.objects.filter(tenant=self.tenant).count(), 1)

    def test_invalid_credentials_and_revocation_block_flow(self):
        self.assertEqual(self.flow(self.payload(), key="invalid").status_code, 401)
        self.assertEqual(self.client.post(self.url, self.payload(), format="json").status_code, 401)
        self.assertFalse(SaleRecord.objects.exists())
        credential = ChannelCredential.objects.get(tenant=self.tenant)
        self.assertTrue(authenticate_flow_key(
            tenant_id=self.tenant.pk, authorization="Bearer " + self.key,
        ))
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["revoked_at"])
        self.assertEqual(self.flow(self.payload()).status_code, 401)

    def test_invalid_payload_is_rejected_and_no_sale(self):
        malformed = [
            {"total_amount": 149.90},
            {"total_amount": "1.001"},
            {"total_amount": "-1.00"},
            {"currency": "USD"},
            {"status": "fulfilled"},
            {"customer_identifier": "31999999999"},
            {"customer_identifier": "bad@email"},
            {"external_order_id": "../wrong"},
            {"channel": "other"},
        ]
        for invalid in malformed:
            with self.subTest(invalid=invalid):
                self.assertEqual(self.flow(self.payload(**invalid)).status_code, 400)
        self.assertFalse(SaleRecord.objects.exists())
        self.assertFalse(CustomerProfile.objects.exists())

    def test_verified_identity_is_reused_across_flow_and_counter_without_credit(self):
        now = timezone.now()
        member = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Cliente",
            contact_email="cliente@example.com", consent_at=now - timedelta(days=3),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="1", status=ProgramParticipant.Status.ACTIVE,
        )
        profile, _ = attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=member.pk,
            email=member.contact_email, proof_method="email_otp",
        )
        first = self.flow(self.payload(
            customer_identifier="CLIENTE@example.com", order="FLOW-100",
        ))
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["identity_status"], "verified_contact_match")
        self.client.force_login(self.owner)
        counter = self.client.post(self.url, self.payload(
            channel="counter", order="COUNTER-12", source_event_id="counter-1",
            customer_identifier="cliente@example.com", status="paid",
        ), format="json")
        self.assertEqual(counter.status_code, 201, counter.data)
        self.assertEqual(CustomerProfile.objects.count(), 1)
        self.assertEqual(set(SaleRecord.objects.values_list("customer_profile_id", flat=True)),
                         {profile.pk})
        self.assertFalse(ChannelCustomerReference.objects.exists())
        counter_sale = SaleRecord.objects.get(channel="counter")
        self.assertEqual(counter_sale.participant_id, member.id)
        self.assertEqual(counter_sale.state, SaleRecord.State.AWAITING_REVIEW)
        self.assert_no_financial_writes()

    def test_unverified_contact_cannot_claim_existing_wallet(self):
        member = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Membro",
            contact_email="identificado@example.com",
            consent_at=timezone.now() - timedelta(days=1),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="1", status=ProgramParticipant.Status.ACTIVE,
        )
        response = self.flow(self.payload(customer_identifier="identificado@example.com"))
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(SaleRecord.objects.get().participant)
        self.assertFalse(VerifiedCustomerContact.objects.exists())
        self.assertFalse(ChannelCustomerReference.objects.exists())
        self.assert_no_financial_writes()

    def test_change_of_customer_on_existing_order_is_rejected(self):
        self.flow(self.payload())
        changed = self.flow(self.payload(
            customer_identifier="+5531988888888", status="paid", source_event_id="evt-101",
        ))
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(SaleEventReceipt.objects.count(), 1)
        self.assertEqual(CustomerProfile.objects.count(), 1)

    def test_manual_pdv_requires_member_session_and_never_automatically_credits(self):
        payload = self.payload(channel="counter", source_event_id="cashier-1")
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 401)
        self.client.force_login(self.analyst)
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 403)
        self.client.force_login(self.owner)
        result = self.client.post(self.url, payload, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(SaleRecord.objects.get().submitted_by_id, self.owner.pk)
        self.assert_no_financial_writes()

    def test_webhook_cannot_impersonate_nuvemshop_via_public_api(self):
        response = self.flow(self.payload(channel="nuvemshop"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(SaleRecord.objects.exists())

    @override_settings(FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED=True)
    def test_nuvemshop_adapter_requires_installation_and_uses_same_sale_record(self):
        snapshot = {
            "external_order_id": "19872", "customer_identifier": "mail@example.com",
            "total_amount": "38.40", "currency": "BRL", "status": "paid",
            "source_event_id": "order-19872-paid",
        }
        with self.assertRaises(NuvemshopSnapshotError):
            ingest_nuvemshop_snapshot(
                tenant_id=self.tenant.pk, store_id="130",
                normalized_snapshot=snapshot,
            )
        NuvemshopInstallation.objects.create(
            tenant=self.tenant, store_id="130", client_id="123",
            token_ciphertext="synthetic-only", scope="read_orders",
        )
        first = ingest_nuvemshop_snapshot(
            tenant_id=self.tenant.pk, store_id="130", normalized_snapshot=snapshot,
        )
        second = ingest_nuvemshop_snapshot(
            tenant_id=self.tenant.pk, store_id="130", normalized_snapshot=snapshot,
        )
        self.assertTrue(first.created)
        self.assertTrue(second.duplicate)
        self.assertEqual(SaleRecord.objects.get().channel, SaleRecord.Channel.NUVEMSHOP)
        self.assertEqual(SaleEventReceipt.objects.count(), 1)
        self.assert_no_financial_writes()

    def test_hmac_secret_rotation_keeps_idempotency(self):
        request = self.payload()
        with override_settings(SECRET_KEY="first-test-key", SECRET_KEY_FALLBACKS=[]):
            initial = self.flow(request)
        with override_settings(
            SECRET_KEY="next-test-key", SECRET_KEY_FALLBACKS=["first-test-key"],
        ):
            retry = self.flow(request)
        self.assertEqual(initial.status_code, 201)
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.data["duplicate"])
        self.assertEqual(SaleEventReceipt.objects.count(), 1)

    def test_no_source_event_id_dedupes_by_order_and_status(self):
        request = self.payload()
        request.pop("source_event_id")
        self.assertEqual(self.flow(request).status_code, 201)
        self.assertTrue(self.flow(request).data["duplicate"])
        request["status"] = "paid"
        self.assertEqual(self.flow(request).status_code, 200)
        self.assertTrue(self.flow(request).data["duplicate"])
        self.assertEqual(SaleEventReceipt.objects.count(), 2)
        self.assert_no_financial_writes()

    def test_flow_key_expiry_is_enforced(self):
        row = ChannelCredential.objects.get(tenant=self.tenant)
        row.expires_at = timezone.now() - timedelta(seconds=1)
        row.save(update_fields=["expires_at"])
        self.assertEqual(self.flow(self.payload()).status_code, 401)

    def test_counter_requires_csrf_for_browser_session(self):
        api = APIClient(enforce_csrf_checks=True)
        api.force_login(self.owner)
        self.assertEqual(api.post(self.url, self.payload(channel="counter"), format="json").status_code, 403)
        api.get(reverse("auth-session"))
        csrf = api.cookies["csrftoken"].value
        result = api.post(
            self.url, self.payload(channel="counter"), format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(result.status_code, 201, result.data)

    def test_receipt_is_append_only(self):
        self.flow(self.payload())
        event = SaleEventReceipt.objects.get()
        event.outcome = SaleEventReceipt.Outcome.IGNORED
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()

    def test_status_timestamp_out_of_order_is_ignored(self):
        older = timezone.now() - timedelta(hours=4)
        newer = older + timedelta(hours=1)
        self.assertEqual(self.flow(self.payload(
            occurred_at=older.isoformat()
        )).status_code, 201)
        self.assertEqual(self.flow(self.payload(
            status="paid", source_event_id="evt-101", occurred_at=newer.isoformat(),
        )).status_code, 200)
        response = self.flow(self.payload(
            status="cancelled", source_event_id="evt-102",
            occurred_at=(older + timedelta(minutes=3)).isoformat(),
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["event_outcome"], "ignored")
        self.assertEqual(SaleRecord.objects.get().order_status, "paid")
