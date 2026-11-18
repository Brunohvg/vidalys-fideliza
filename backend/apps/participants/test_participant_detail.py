"""Página do cliente no painel: detalhe isolado por loja e pausa só por administradores."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant, TenantMembership
from .models import ProgramParticipant


@override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=False, FIDELIZA_POINTS_WRITES_ENABLED=False)
class ParticipantDetailTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="detail-owner")
        self.analyst = User.objects.create_user(username="detail-analyst")
        self.tenant = Tenant.objects.create(name="Loja Detalhe", slug="loja-detalhe",
                                            platform="independent", status=Tenant.Status.ACTIVE)
        self.other = Tenant.objects.create(name="Outra", slug="outra-detalhe",
                                           platform="independent", status=Tenant.Status.ACTIVE)
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role=TenantMembership.Role.OWNER)
        TenantMembership.objects.create(user=self.owner, tenant=self.other, role=TenantMembership.Role.OWNER)
        TenantMembership.objects.create(user=self.analyst, tenant=self.tenant, role=TenantMembership.Role.ANALYST)
        self.ana = ProgramParticipant.objects.create(
            tenant=self.tenant, display_name="Ana Detalhe", contact_email="ana@example.invalid",
            external_customer_id=None, consent_at=timezone.now() - timedelta(days=3),
            consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL, terms_version="v1",
            status=ProgramParticipant.Status.ACTIVE,
        )
        SaleRecord.objects.create(
            tenant=self.tenant, participant=self.ana, channel=SaleRecord.Channel.COUNTER,
            external_reference="DET-1", eligible_amount_cents=4590, reported_paid_at=timezone.now(),
            state=SaleRecord.State.AWAITING_REVIEW,
        )

    def _client(self, user):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        client.get(reverse("auth-session"))
        return client

    def _status(self, client, status, tenant=None):
        client.get(reverse("auth-session"))
        return client.post(reverse("tenant-participant-status", kwargs={
            "tenant_id": (tenant or self.tenant).id, "participant_id": self.ana.id}),
            {"status": status}, format="json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)

    def test_detail_shows_sales_and_profile_without_other_store(self):
        client = self._client(self.owner)
        url = reverse("tenant-participant-detail", kwargs={"tenant_id": self.tenant.id, "participant_id": self.ana.id})
        data = client.get(url).json()
        self.assertEqual(data["participant"]["display_name"], "Ana Detalhe")
        self.assertEqual(data["sales"][0]["amount_cents"], 4590)
        self.assertEqual(data["sales"][0]["state"], "awaiting_review")
        self.assertIn("birth_month", data["profile"])
        other = reverse("tenant-participant-detail", kwargs={"tenant_id": self.other.id, "participant_id": self.ana.id})
        self.assertEqual(client.get(other).status_code, 404)

    def test_owner_pauses_and_resumes_but_analyst_cannot(self):
        owner = self._client(self.owner)
        paused = self._status(owner, "paused")
        self.assertEqual(paused.status_code, 200)
        self.assertEqual(paused.json()["participant"]["status"], "paused")
        self.assertFalse(paused.json()["points_credited"])
        self.assertEqual(self._status(owner, "active").json()["participant"]["status"], "active")
        self.assertEqual(self._status(owner, "withdrawn").status_code, 400)
        self.assertEqual(self._status(self._client(self.analyst), "paused").status_code, 403)
        self.assertEqual(self._status(owner, "paused", tenant=self.other).status_code, 404)
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.status, "active")
