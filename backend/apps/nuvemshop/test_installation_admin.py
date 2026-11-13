"""Admin de OAuth em leitura, sem revelar credenciais nem mudar a loja."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.tenants.models import Tenant
from apps.nuvemshop.models import NuvemshopInstallation


@override_settings(STORAGES={
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
})
class InstallationAdminSafetyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="oauth-auditor", password="synthetic-strong-2026",
            email="oauth-auditor@example.invalid",
        )
        self.staff = User.objects.create_user(
            username="qa-staff", password="synthetic-strong-2026",
            email="staff@example.invalid", is_staff=True,
        )
        self.tenant = Tenant.objects.create(
            name="Loja Piloto QA", slug="oauth-pilot-qa",
            platform="nuvemshop", external_store_id="42123",
            status=Tenant.Status.ACTIVE,
        )
        self.installation = NuvemshopInstallation.objects.create(
            tenant=self.tenant, client_id="123456", store_id="42123",
            token_ciphertext="encrypted-token-synthetic-must-not-leak-123",
            scope="read_products", connected_by=self.superuser,
        )
        self.client = Client()
        self.list_url = reverse("admin:nuvemshop_nuvemshopinstallation_changelist")
        self.detail_url = reverse(
            "admin:nuvemshop_nuvemshopinstallation_change",
            args=[self.installation.pk],
        )

    def test_superuser_sees_store_and_consistency_but_not_token(self):
        self.client.force_login(self.superuser)
        listing = self.client.get(self.list_url)
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Loja Piloto QA")
        self.assertContains(listing, "Consistente (token não verificado)")
        self.assertNotContains(listing, "encrypted-token-synthetic")
        detail = self.client.get(self.detail_url)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "read_products")
        self.assertNotContains(detail, "encrypted-token-synthetic")
        self.assertNotContains(detail, "token_ciphertext")

    def test_inconsistent_pair_is_visible_not_fixed(self):
        self.tenant.external_store_id = "99999"
        self.tenant.save(update_fields=["external_store_id"])
        self.client.force_login(self.superuser)
        self.assertContains(self.client.get(self.list_url), "DIVERGENTE")
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.store_id, "42123")
        self.assertEqual(self.tenant.external_store_id, "99999")

    def test_neither_user_nor_installation_is_editable_from_admin(self):
        self.client.force_login(self.superuser)
        response = self.client.post(self.detail_url, {
            "store_id": "99999",
            "client_id": "999",
            "token_ciphertext": "replacement-token",
        })
        self.assertEqual(response.status_code, 403)
        self.installation.refresh_from_db()
        self.assertEqual(self.installation.store_id, "42123")
        self.assertEqual(
            self.installation.token_ciphertext,
            "encrypted-token-synthetic-must-not-leak-123",
        )
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.list_url).status_code, 302)
