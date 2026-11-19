"""Endereço do clube: limpo, editável e sem quebrar links antigos."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .club_address import canonical_slug, first_free_address, normalize_address
from .models import Tenant, TenantMembership, TenantSlugAlias


class ClubAddressTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="addr-owner")
        self.analyst = User.objects.create_user(username="addr-analyst")
        self.tenant = Tenant.objects.create(name="Loja Bonita", slug="loja-bonita-3f9a2b1c4d5e",
                                            platform="independent", status=Tenant.Status.ACTIVE)
        self.other = Tenant.objects.create(name="Outra", slug="outra-loja",
                                           platform="independent", status=Tenant.Status.ACTIVE)
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role=TenantMembership.Role.OWNER)
        TenantMembership.objects.create(user=self.analyst, tenant=self.tenant,
                                        role=TenantMembership.Role.ANALYST)

    def _client(self, user):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        client.get(reverse("auth-session"))
        return client

    def _change(self, slug, user=None, tenant=None):
        client = self._client(user or self.owner)
        return client.post(
            reverse("tenant-club-address", kwargs={"tenant_id": (tenant or self.tenant).id}),
            {"slug": slug}, format="json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )

    def test_normalize_rejects_reserved_and_short(self):
        self.assertEqual(normalize_address(" Loja Bonita "), "loja-bonita")
        for bad in ("ab", "api", "entrar", "", "---"):
            with self.assertRaises(ValueError):
                normalize_address(bad)

    def test_new_store_gets_clean_address(self):
        self.assertEqual(first_free_address("Armarinho da Ana"), "armarinho-da-ana")
        Tenant.objects.create(name="Outra", slug="armarinho-da-ana", platform="independent")
        self.assertEqual(first_free_address("Armarinho da Ana"), "armarinho-da-ana-2")

    def test_owner_changes_address_and_old_link_keeps_working(self):
        response = self._change("loja-bonita")
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.slug, "loja-bonita")
        self.assertTrue(TenantSlugAlias.objects.filter(slug="loja-bonita-3f9a2b1c4d5e").exists())
        self.assertEqual(canonical_slug("loja-bonita-3f9a2b1c4d5e"), "loja-bonita")
        old = self.client.get(reverse("member-club-public", kwargs={"slug": "loja-bonita-3f9a2b1c4d5e"}))
        self.assertEqual(old.status_code, 200)
        self.assertEqual(old.json()["store_slug"], "loja-bonita")
        self.assertIsNone(old.json()["earning"])

    def test_cannot_take_address_of_another_store_or_its_alias(self):
        self.assertEqual(self._change("outra-loja").status_code, 409)
        TenantSlugAlias.objects.create(slug="nome-antigo", tenant=self.other)
        self.assertEqual(self._change("nome-antigo").status_code, 409)

    def test_store_can_return_to_its_own_old_address(self):
        self._change("loja-bonita")
        self.assertEqual(self._change("loja-bonita-3f9a2b1c4d5e").status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.slug, "loja-bonita-3f9a2b1c4d5e")
        self.assertFalse(TenantSlugAlias.objects.filter(slug="loja-bonita-3f9a2b1c4d5e").exists())

    def test_only_admins_change_address(self):
        self.assertEqual(self._change("nova-loja", user=self.analyst).status_code, 403)
        self.assertEqual(self._change("nova-loja", tenant=self.other).status_code, 404)
