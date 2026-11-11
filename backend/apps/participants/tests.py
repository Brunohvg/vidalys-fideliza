"""Participantes reais exigem aceite explícito; testes usam dados sintéticos."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership
from .models import ProgramParticipant


class ParticipantDirectoryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="loyalty-owner")
        self.analyst = User.objects.create_user(username="loyalty-analyst")
        self.stranger = User.objects.create_user(username="loyalty-stranger")
        self.tenant = Tenant.objects.create(name="Loja piloto", slug="members-a")
        self.other = Tenant.objects.create(name="Outra loja", slug="members-b")
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role="owner")
        TenantMembership.objects.create(user=self.analyst, tenant=self.tenant, role="analyst")
        TenantMembership.objects.create(user=self.stranger, tenant=self.other, role="owner")
        self.client = APIClient()

    def path(self, tenant=None):
        return reverse("tenant-participants", kwargs={"tenant_id": tenant or self.tenant.pk})

    def member(self, *, tenant=None, customer="101", name="Cliente consentido",
               email="cliente@example.invalid", status="active"):
        return ProgramParticipant.objects.create(
            tenant=tenant or self.tenant,
            external_customer_id=customer, display_name=name, contact_email=email,
            consent_at=timezone.now() - timedelta(days=3),
            consent_channel="customer_portal", terms_version="v1",
            status=status,
        )

    def test_anonymous_requires_login(self):
        response = self.client.get(self.path())
        self.assertIn(response.status_code, (401, 403))

    def test_empty_does_not_misrepresent_all_store_customers(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get(self.path())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["source"], "verified_opt_in_only")
        self.assertEqual(r.data["data_status"], "no_enrollment_channel")
        self.assertEqual(r.data["summary"]["total"], 0)
        self.assertEqual(r.data["items"], [])
        self.assertNotIn("read_customers", str(r.data))

    def test_does_not_leak_other_tenant_and_excludes_withdrawn(self):
        self.member(customer="1", name="Primeiro participante")
        self.member(customer="2", name="Aceite encerrado", status="withdrawn")
        self.member(tenant=self.other, customer="3", name="SEGREDO OUTRA LOJA")
        self.client.force_authenticate(self.owner)
        r = self.client.get(self.path())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["summary"]["total"], 1)
        self.assertEqual(len(r.data["items"]), 1)
        self.assertEqual(r.data["items"][0]["display_name"], "Primeiro participante")
        self.assertNotIn("SEGREDO", str(r.data))
        self.assertEqual(r["Cache-Control"], "private, no-store")
        self.assertIsNone(r.data["items"][0]["points_balance"])
        self.assertIsNone(r.data["items"][0]["cashback_balance_cents"])
        self.assertEqual(r.data["items"][0]["balance_status"], "not_implemented")

    def test_member_can_read_but_not_create_from_admin_api(self):
        self.member(customer="4", name="Consentido")
        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.get(self.path()).status_code, 200)
        self.assertEqual(self.client.post(self.path(), {"name": "Sem consentimento"}, format="json").status_code, 405)
        self.assertEqual(ProgramParticipant.objects.count(), 1)

    def test_foreign_tenant_hidden(self):
        self.member()
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(self.path()).status_code, 404)

    def test_filters_search_and_pagination(self):
        self.member(customer="101", name="Mariana", status="active")
        self.member(customer="102", name="João", status="paused")
        self.client.force_authenticate(self.owner)
        active = self.client.get(self.path(), {"status": "active"})
        self.assertEqual(active.data["summary"]["total"], 2)
        self.assertEqual(active.data["summary"]["paused"], 1)
        self.assertEqual(active.data["total_filtered"], 1)
        self.assertEqual(active.data["items"][0]["display_name"], "Mariana")
        match = self.client.get(self.path(), {"q": "joão"})
        self.assertEqual(match.data["total_filtered"], 1)
        self.assertEqual(match.data["items"][0]["status"], "paused")
        later = self.client.get(self.path(), {"offset": "20"})
        self.assertEqual(later.data["items"], [])
        for query in ({"offset": "-1"}, {"offset": "1.0"}, {"status": "withdrawn"},
                      {"q": "x" * 81}, {"offset": "9" * 100}):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.path(), query).status_code, 400)

    def test_same_external_customer_can_join_two_tenants_independently(self):
        self.member(customer="909", name="Loja A")
        self.member(tenant=self.other, customer="909", name="Loja B")
        self.assertEqual(ProgramParticipant.objects.count(), 2)
