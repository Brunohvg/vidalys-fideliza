"""PR23 — balcão chama o mesmo core de ingestão idempotente dos demais canais."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.participants.models import ProgramParticipant
from apps.customers.services import attach_verified_contact
from apps.sales.models import SaleEventReceipt, SaleRecord, SaleManualLinkAudit
from apps.tenants.models import Tenant, TenantMembership
from apps.loyalty.models import LoyaltyGrant
from apps.points.models import PointEntry
from apps.wallets.models import CashbackEntry


class CounterUnifiedAdapterTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="PDV pr23", slug="pdv-pr23", status=Tenant.Status.ACTIVE,
        )
        self.owner = get_user_model().objects.create_user(username="pdv-pr23-owner")
        TenantMembership.objects.create(
            tenant=self.tenant, user=self.owner, role=TenantMembership.Role.OWNER,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)
        self.url = reverse("manual-sales", kwargs={"tenant_id": self.tenant.pk})

    def payload(self, receipt, participant=None):
        return {
            "reference": receipt,
            "eligible_amount_cents": 12990,
            "participant_id": str(participant.pk) if participant else None,
            "reported_paid_at": timezone.now().isoformat(),
            "evidence_reference": receipt,
        }

    def test_unidentified_sale_uses_single_event_service_no_credit(self):
        data = self.payload("PDV-SEM-CLIENTE-001")
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        record = SaleRecord.objects.get(pk=response.data["sale"]["id"])
        self.assertEqual(record.channel, SaleRecord.Channel.COUNTER)
        self.assertEqual(record.state, SaleRecord.State.AWAITING_MEMBER)
        self.assertIsNone(record.customer_profile_id)
        self.assertEqual(record.order_status, SaleRecord.OrderStatus.PAID)
        self.assertEqual(record.reported_total_cents, 12990)
        self.assertEqual(record.eligible_amount_cents, 12990)
        self.assertTrue(record.source_order_key)
        self.assertEqual(record.inbound_events.count(), 1)
        self.assertFalse(response.data["payment_verified"])
        again = self.client.post(self.url, data, format="json")
        self.assertEqual(again.status_code, 200, again.data)
        self.assertTrue(again.data["already_recorded"])
        self.assertEqual(SaleEventReceipt.objects.count(), 1)
        self.assertFalse(LoyaltyGrant.objects.exists())
        self.assertFalse(PointEntry.objects.exists())
        self.assertFalse(CashbackEntry.objects.exists())

    def test_selected_member_stays_manual_review_without_financial_evidence(self):
        participant = ProgramParticipant.objects.create(
            tenant=self.tenant, status="active",
            consent_at=timezone.now(), consent_channel="customer_portal",
            terms_version="v1", display_name="Participante PDV",
        )
        # O registro legado sem OTP não autoriza vinculação de carteira.
        data = self.payload("PDV-COM-MEMBRO-001", participant)
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        sale = SaleRecord.objects.get(pk=response.data["sale"]["id"])
        self.assertEqual(sale.participant_id, participant.pk)
        self.assertIsNone(sale.customer_profile_id)
        self.assertEqual(sale.state, SaleRecord.State.AWAITING_REVIEW)
        self.assertEqual(response.data["identity_status"], "awaiting_verified_identity")
        self.assertEqual(SaleEventReceipt.objects.filter(sale=sale).count(), 1)
        self.assertFalse(LoyaltyGrant.objects.exists())


    def test_unidentified_counter_sale_can_link_verified_member_later(self):
        sale_created = self.client.post(
            self.url, self.payload("PDV-LATER-001"), format="json",
        )
        self.assertEqual(sale_created.status_code, 201)
        member = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Pessoa com OTP",
            contact_email="pdv-late@example.invalid", status="active",
            consent_at=timezone.now(), consent_channel="customer_portal", terms_version="v1",
        )
        sale_id = sale_created.data["sale"]["id"]
        link_url = reverse("manual-sale-link", kwargs={
            "tenant_id": self.tenant.pk, "sale_id": sale_id,
        })
        no_otp = self.client.post(
            link_url, {"participant_id": str(member.pk)}, format="json",
        )
        self.assertEqual(no_otp.status_code, 409)
        attach_verified_contact(
            tenant_id=self.tenant.pk, participant_id=member.pk,
            email=member.contact_email, proof_method="email_otp",
        )
        linked = self.client.post(
            link_url, {"participant_id": str(member.pk)}, format="json",
        )
        self.assertEqual(linked.status_code, 200, linked.data)
        sale = SaleRecord.objects.get(pk=sale_id)
        self.assertEqual(sale.participant_id, member.pk)
        self.assertIsNotNone(sale.customer_profile_id)
        self.assertEqual(sale.state, SaleRecord.State.AWAITING_REVIEW)
        self.assertEqual(SaleManualLinkAudit.objects.get(sale=sale).participant_id, member.pk)
        self.assertEqual(SaleEventReceipt.objects.filter(sale=sale).count(), 1)
        self.assertEqual(
            self.client.post(link_url, {"participant_id": str(member.pk)}, format="json").status_code,
            409,
        )
        self.assertFalse(linked.data["points_credited"])
        self.assertFalse(LoyaltyGrant.objects.exists())
