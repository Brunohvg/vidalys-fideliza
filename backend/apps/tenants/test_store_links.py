"""Acesso e auditoria dos vínculos conta-empresa, sem reparo automático."""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import MerchantEmailIdentity, MerchantRegistration
from apps.tenants.management.commands.audit_store_links import inspect_store_links
from apps.tenants.models import Tenant, TenantMembership


class StoreLinkAuditTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.linked = User.objects.create_user(
            username="linked", email="linked@example.invalid",
        )
        self.orphan = User.objects.create_user(
            username="orphan", email="orphan@example.invalid",
        )
        self.technical = User.objects.create_superuser(
            username="technical", email="technical@example.invalid",
            password="only-synthetic-password-2026",
        )
        for user in (self.linked, self.orphan):
            MerchantEmailIdentity.objects.create(
                user=user, normalized_email=user.email,
                verified_at=timezone.now(),
            )
        self.store = Tenant.objects.create(
            name="Loja Confirmada", slug="loja-confirmada",
            status=Tenant.Status.ACTIVE, platform="independent",
        )
        self.store_without_owner = Tenant.objects.create(
            name="Loja órfã", slug="loja-orfa",
            status=Tenant.Status.ACTIVE, platform="independent",
        )
        TenantMembership.objects.create(
            user=self.linked, tenant=self.store,
            role=TenantMembership.Role.OWNER,
        )
        MerchantRegistration.objects.create(
            normalized_email="pending@example.invalid",
            first_name="Teste", store_name="Ainda não confirmada",
            password_hash="fake-only-test",
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def test_readonly_audit_classifies_verified_orphans_and_technical_staff(self):
        report = inspect_store_links()
        self.assertEqual(report["verified_merchants"], 2)
        self.assertEqual(report["verified_without_store"], 1)
        self.assertEqual(report["stores_without_owner"], 1)
        self.assertEqual(report["staff_without_store"], 1)
        self.assertEqual(report["pending_confirmations"], 1)
        self.assertEqual(TenantMembership.objects.count(), 1)

    def test_command_does_not_leak_personal_data_or_create_links(self):
        output = StringIO()
        call_command("audit_store_links", stdout=output)
        text = output.getvalue()
        self.assertIn("verified_without_store=1", text)
        self.assertIn("stores_without_owner=1", text)
        self.assertNotIn("orphan@example.invalid", text)
        self.assertNotIn("Loja órfã", text)
        self.assertEqual(TenantMembership.objects.count(), 1)
        with self.assertRaises(CommandError):
            call_command("audit_store_links", "--strict", stdout=StringIO())

    @override_settings(STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    })
    def test_admin_shows_owned_and_unowned_stores_and_readonly_links(self):
        self.client.force_login(self.technical)
        stores_page = self.client.get(
            reverse("admin:tenants_tenant_changelist")
        )
        self.assertEqual(stores_page.status_code, 200)
        self.assertContains(stores_page, "Proprietários")
        members_url = reverse("admin:tenants_tenantmembership_changelist")
        self.assertEqual(self.client.get(members_url).status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse("admin:tenants_tenantmembership_change",
                        args=[TenantMembership.objects.get().pk]),
                {},
            ).status_code,
            403,
        )
        self.client.force_login(self.linked)
        self.assertEqual(self.client.get(members_url).status_code, 302)
