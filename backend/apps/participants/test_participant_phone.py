"""Celular como identificador no balcão: HMAC por loja, isolamento e sem crédito."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sales.models import SaleRecord
from apps.tenants.models import Tenant, TenantMembership
from .models import ProgramParticipant
from .phone import normalize_br_phone


class NormalizePhoneTests(SimpleTestCase):
    def test_accepts_common_brazilian_formats(self):
        for raw in ("(31) 99999-8888", "31999998888", "+55 31 99999-8888", "5531999998888"):
            self.assertEqual(normalize_br_phone(raw), "+5531999998888")
        self.assertEqual(normalize_br_phone("(31) 3333-4444"), "+553133334444")

    def test_rejects_incomplete_or_foreign_numbers(self):
        for raw in ("99999-8888", "+1 202 555 0100", "(01) 99999-8888", "31899998888", "", "abc"):
            with self.assertRaises(ValueError):
                normalize_br_phone(raw)


@override_settings(FIDELIZA_LEDGER_WRITES_ENABLED=False, FIDELIZA_POINTS_WRITES_ENABLED=False)
class ParticipantPhoneTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="phone-owner")
        self.analyst = User.objects.create_user(username="phone-analyst")
        self.tenant = Tenant.objects.create(name="Loja Celular", slug="loja-celular",
                                            platform="independent", status=Tenant.Status.ACTIVE)
        self.other = Tenant.objects.create(name="Outra Loja", slug="outra-celular",
                                           platform="independent", status=Tenant.Status.ACTIVE)
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role=TenantMembership.Role.OWNER)
        TenantMembership.objects.create(user=self.owner, tenant=self.other, role=TenantMembership.Role.OWNER)
        TenantMembership.objects.create(user=self.analyst, tenant=self.tenant, role=TenantMembership.Role.ANALYST)
        now = timezone.now() - timedelta(days=1)
        self.ana = self._member(self.tenant, "Ana Souza", "ana@example.invalid", now)
        self.bia = self._member(self.tenant, "Bia Lima", "bia@example.invalid", now)
        self.client = self._client(self.owner)

    def _member(self, tenant, name, email, when):
        return ProgramParticipant.objects.create(
            tenant=tenant, display_name=name, contact_email=email, external_customer_id=None,
            consent_at=when, consent_channel=ProgramParticipant.ConsentChannel.CUSTOMER_PORTAL,
            terms_version="v1", status=ProgramParticipant.Status.ACTIVE,
        )

    def _client(self, user):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        client.get(reverse("auth-session"))
        return client

    def _post(self, client, name, payload, **kwargs):
        client.get(reverse("auth-session"))
        return client.post(reverse(name, kwargs=kwargs), payload, format="json",
                           HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)

    def _set_phone(self, participant, phone, client=None, tenant=None):
        return self._post(client or self.client, "tenant-participant-phone",
                          {"phone": phone, "customer_informed": True},
                          tenant_id=(tenant or self.tenant).id, participant_id=participant.id)

    def _lookup(self, phone, client=None, tenant=None):
        return self._post(client or self.client, "tenant-participant-by-phone", {"phone": phone},
                          tenant_id=(tenant or self.tenant).id)

    def test_owner_sets_phone_and_finds_participant_without_exposing_number(self):
        response = self._set_phone(self.ana, "(31) 99999-8888")
        self.assertEqual(response.status_code, 200)
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.phone_last4, "8888")
        self.assertEqual(len(self.ana.phone_digest), 64)
        self.assertNotIn("99999", self.ana.phone_digest)
        found = self._lookup("31 99999 8888")
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()["match"]["id"], str(self.ana.id))
        self.assertNotIn("999998888", found.content.decode())
        self.assertEqual(found["Cache-Control"], "private, no-store")

    def test_same_phone_cannot_belong_to_two_participants(self):
        self.assertEqual(self._set_phone(self.ana, "31999998888").status_code, 200)
        self.assertEqual(self._set_phone(self.bia, "+55 31 99999-8888").status_code, 409)

    def test_phone_requires_customer_confirmation_and_valid_number(self):
        response = self._post(self.client, "tenant-participant-phone",
                              {"phone": "31999998888", "customer_informed": False},
                              tenant_id=self.tenant.id, participant_id=self.ana.id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._set_phone(self.ana, "9999-8888").status_code, 400)
        self.assertEqual(self._lookup("123").status_code, 400)

    def test_analyst_and_other_tenant_cannot_use_phone(self):
        self._set_phone(self.ana, "31999998888")
        analyst = self._client(self.analyst)
        self.assertEqual(self._lookup("31999998888", client=analyst).status_code, 403)
        self.assertEqual(self._set_phone(self.bia, "31977776666", client=analyst).status_code, 403)
        # Mesmo número em outra loja não encontra o participante desta.
        self.assertIsNone(self._lookup("31999998888", tenant=self.other).json()["match"])
        # Participante de uma loja não pode ser alterado pela URL de outra.
        self.assertEqual(self._set_phone(self.bia, "31977776666", tenant=self.other).status_code, 404)

    def test_phone_digest_is_per_tenant(self):
        twin = self._member(self.other, "Ana em outra loja", "ana2@example.invalid", timezone.now())
        self._set_phone(self.ana, "31999998888")
        self.assertEqual(self._set_phone(twin, "31999998888", tenant=self.other).status_code, 200)
        self.ana.refresh_from_db(); twin.refresh_from_db()
        self.assertNotEqual(self.ana.phone_digest, twin.phone_digest)

    def test_counter_sale_without_member_keeps_phone_and_suggests_link_later(self):
        sale = self._post(self.client, "manual-sales", {
            "reference": "VENDA-CEL-1", "eligible_amount_cents": 5990, "participant_id": None,
            "reported_paid_at": timezone.now().isoformat(), "evidence_reference": "CUPOM-CEL-1",
            "customer_phone": "(31) 98888-7777",
        }, tenant_id=self.tenant.id)
        self.assertEqual(sale.status_code, 201)
        record = SaleRecord.objects.get(tenant=self.tenant, external_reference="VENDA-CEL-1")
        self.assertEqual(record.state, SaleRecord.State.AWAITING_MEMBER)
        self.assertEqual(len(record.counter_phone_digest), 64)
        self.assertFalse(sale.json()["points_credited"])
        listed = self.client.get(reverse("manual-sales", kwargs={"tenant_id": self.tenant.id})).json()
        self.assertIsNone(listed["items"][0]["suggested_participant"])
        self._set_phone(self.bia, "31988887777")
        listed = self.client.get(reverse("manual-sales", kwargs={"tenant_id": self.tenant.id})).json()
        self.assertEqual(listed["items"][0]["suggested_participant"]["id"], str(self.bia.id))
        record.refresh_from_db()
        self.assertIsNone(record.participant_id)

    def test_counter_sale_rejects_invalid_phone(self):
        response = self._post(self.client, "manual-sales", {
            "reference": "VENDA-CEL-2", "eligible_amount_cents": 1000, "participant_id": None,
            "reported_paid_at": timezone.now().isoformat(), "evidence_reference": "CUPOM-CEL-2",
            "customer_phone": "12345",
        }, tenant_id=self.tenant.id)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SaleRecord.objects.filter(external_reference="VENDA-CEL-2").exists())

    def test_participant_list_shows_only_last_digits(self):
        self._set_phone(self.ana, "31999998888")
        data = self.client.get(reverse("tenant-participants", kwargs={"tenant_id": self.tenant.id})).json()
        row = next(item for item in data["items"] if item["id"] == str(self.ana.id))
        self.assertEqual(row["phone_last4"], "8888")
        self.assertNotIn("999998888", str(data))
