import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.tenants.models import Tenant, TenantMembership


class SessionApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="lojista", password="not-a-real-password-123", first_name="Loja"
        )
        self.other = get_user_model().objects.create_user(
            username="outra", password="not-a-real-password-123"
        )
        self.store = Tenant.objects.create(name="Bibelô Piloto", slug="bibelo-teste")
        self.other_store = Tenant.objects.create(name="Outra Loja", slug="outra-loja")
        TenantMembership.objects.create(
            user=self.user, tenant=self.store, role=TenantMembership.Role.OWNER
        )
        TenantMembership.objects.create(
            user=self.other, tenant=self.other_store, role=TenantMembership.Role.ADMIN
        )
        self.client = Client(enforce_csrf_checks=True)

    def _csrf(self):
        self.client.get(reverse("auth-session"))
        return self.client.cookies["csrftoken"].value

    def _login(self, username="lojista", password="not-a-real-password-123", with_csrf=True):
        token = self._csrf() if with_csrf else ""
        return self.client.post(
            reverse("auth-login"),
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
            **({"HTTP_X_CSRFTOKEN": token} if with_csrf else {}),
        )

    def test_anonymous_session_sets_csrf_cookie_and_discloses_no_data(self):
        response = self.client.get(reverse("auth-session"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["authenticated"], False)
        self.assertEqual(response.json()["tenants"], [])
        self.assertIn("csrftoken", response.cookies)
        self.assertIn("no-store", response.get("Cache-Control", ""))

    def test_login_requires_csrf_even_when_anonymous(self):
        self.assertEqual(self._login(with_csrf=False).status_code, 403)

    def test_login_success_and_only_owned_store(self):
        response = self._login()
        self.assertEqual(response.status_code, 200)
        session = self.client.get(reverse("auth-session")).json()
        self.assertEqual(session["user"]["username"], "lojista")
        self.assertEqual(len(session["tenants"]), 1)
        self.assertEqual(session["store_link_status"], "linked")
        self.assertEqual(session["tenants"][0]["name"], "Bibelô Piloto")
        self.assertNotIn("Outra Loja", str(session))

    def test_legacy_staff_account_is_not_silently_linked_to_a_store(self):
        staff = get_user_model().objects.create_superuser(
            username="technical-admin", email="technical@example.invalid",
            password="strong-synthetic-2026",
        )
        self.client.force_login(staff)
        session = self.client.get(reverse("auth-session")).json()
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["store_link_status"], "missing")
        self.assertEqual(session["tenants"], [])
        self.assertFalse(TenantMembership.objects.filter(user=staff).exists())
        self.assertEqual(TenantMembership.objects.count(), 2)

    def test_bad_password_and_bruteforce_limit(self):
        for _ in range(8):
            self.assertEqual(self._login(password="invalid").status_code, 401)
        self.assertEqual(self._login(password="invalid").status_code, 429)
        self.assertEqual(self._login().status_code, 429)

    def test_logout_requires_csrf_and_revokes_session(self):
        self.assertEqual(self._login().status_code, 200)
        self.assertEqual(self.client.post(reverse("auth-logout")).status_code, 403)
        token = self.client.cookies["csrftoken"].value
        response = self.client.post(reverse("auth-logout"), HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.get(reverse("auth-session")).json()["authenticated"])

    def test_authenticated_margin_api_requires_csrf(self):
        self.assertEqual(self._login().status_code, 200)
        payload = {
            "eligible_subtotal_cents": 20000,
            "existing_discounts_cents": 1000,
            "cost_of_goods_cents": 10000,
        }
        url = reverse("tenant-margin-simulation", kwargs={"tenant_id": self.store.pk})
        self.assertEqual(
            self.client.post(url, data=json.dumps(payload), content_type="application/json").status_code,
            403,
        )
        token = self.client.cookies["csrftoken"].value
        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["automatically_approved"])

    def test_logged_in_user_cannot_simulate_other_tenant(self):
        self.assertEqual(self._login().status_code, 200)
        token = self.client.cookies["csrftoken"].value
        url = reverse("tenant-margin-simulation", kwargs={"tenant_id": self.other_store.pk})
        response = self.client.post(
            url, data=json.dumps({"eligible_subtotal_cents": 10000}),
            content_type="application/json", HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 404)

    def test_rejects_bad_input_without_echoing_password(self):
        token = self._csrf()
        response = self.client.post(reverse("auth-login"), data="not-json",
            content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("password", response.content.decode("utf8"))
