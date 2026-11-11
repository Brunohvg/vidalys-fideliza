"""Auth and read-only catalogue tests; no Nuvemshop network requests or real credentials."""
import json
import os
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.costs.models import CostAudit, CostItem
from apps.tenants.models import Tenant, TenantMembership
from .models import NuvemshopInstallation, OAuthAttempt
from .provider import OAuthExchangeError, exchange_code
from .security import config, decrypt_token, digest, encrypt_token


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return None

    def read(self, size):
        return self.payload[:size]


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.last_request = None
        self.timeout = None

    def open(self, request, timeout=None):
        self.last_request = request
        self.timeout = timeout
        return FakeResponse(self.response)


class TokenSecurityTests(SimpleTestCase):
    def test_fernet_encrypts_and_rotates_keys(self):
        original = Fernet.generate_key().decode()
        rotated = Fernet.generate_key().decode()
        cipher = encrypt_token("opaque-token-synthetic", original)
        self.assertNotIn("opaque-token-synthetic", cipher)
        self.assertEqual(decrypt_token(cipher, rotated + "," + original), "opaque-token-synthetic")
        new_cipher = encrypt_token("new-synthetic", rotated + "," + original)
        self.assertEqual(decrypt_token(new_cipher, rotated + "," + original), "new-synthetic")

    def test_provider_fixed_url_body_and_strict_scopes(self):
        good = {
            "access_token": "synthetic-opaque-token-123", "token_type": "bearer",
            "scope": "read_products", "user_id": 5432,
        }
        transport = FakeOpener(good)
        result = exchange_code("synthetic-code-123", "12345", "synthetic-secret",
                               opener=transport)
        self.assertEqual(result["store_id"], "5432")
        self.assertEqual(result["scope"], "read_products")
        self.assertEqual(transport.last_request.full_url,
                         "https://www.tiendanube.com/apps/authorize/token")
        self.assertEqual(transport.last_request.get_method(), "POST")
        self.assertEqual(transport.timeout, 8)
        posted = json.loads(transport.last_request.data)
        self.assertEqual(posted["grant_type"], "authorization_code")
        self.assertEqual(posted["client_id"], "12345")
        self.assertEqual(posted["code"], "synthetic-code-123")
        for scopes in ("read_products,write_products", "read_orders", ""):
            with self.subTest(scope=scopes), self.assertRaises(OAuthExchangeError):
                exchange_code("synthetic-code-123", "12345", "synthetic-secret",
                              opener=FakeOpener({**good, "scope": scopes}))

    def test_provider_rejects_bad_store_ids(self):
        for user_id in (None, 0, "-10", "https://invalid.example", True):
            with self.subTest(user_id=user_id), self.assertRaises(OAuthExchangeError):
                exchange_code("synthetic-code-123", "12345", "synthetic-secret",
                              opener=FakeOpener({
                                  "access_token": "synthetic-opaque-token-123",
                                  "token_type": "bearer", "scope": "read_products",
                                  "user_id": user_id,
                              }))


class NuvemshopOAuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.cipher_key = Fernet.generate_key().decode()
        self.env = patch.dict(os.environ, {
            "NUVEMSHOP_CLIENT_ID": "12345",
            "NUVEMSHOP_CLIENT_SECRET": "synthetic-client-secret",
            "NUVEMSHOP_TOKEN_KEYS": self.cipher_key,
            "NUVEMSHOP_OAUTH_CALLBACK_URL":
                "https://testserver/api/v1/oauth/nuvemshop/callback/",
            "NUVEMSHOP_API_USER_AGENT": "Fideliza QA (qa@example.invalid)",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        User = get_user_model()
        self.owner = User.objects.create_user(username="oauth-owner")
        self.analyst = User.objects.create_user(username="oauth-analyst")
        self.foreign_user = User.objects.create_user(username="oauth-foreign")
        self.tenant = Tenant.objects.create(name="Merchant A", slug="oauth-a")
        self.foreign = Tenant.objects.create(name="Merchant B", slug="oauth-b")
        TenantMembership.objects.create(user=self.owner, tenant=self.tenant, role="owner")
        TenantMembership.objects.create(user=self.analyst, tenant=self.tenant, role="analyst")
        TenantMembership.objects.create(user=self.foreign_user, tenant=self.foreign, role="owner")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.client.get("/api/v1/auth/session/", secure=True)

    def start_url(self, tenant=None):
        return reverse("nuvemshop-connect", kwargs={
            "tenant_id": tenant or self.tenant.pk
        })

    def status_url(self, tenant=None):
        return reverse("nuvemshop-status", kwargs={
            "tenant_id": tenant or self.tenant.pk
        })

    def preview_url(self, tenant=None):
        return reverse("nuvemshop-catalog-preview", kwargs={
            "tenant_id": tenant or self.tenant.pk
        })

    def start(self, tenant=None):
        csrf = self.client.cookies["csrftoken"].value
        response = self.client.post(
            self.start_url(tenant), data="{}", content_type="application/json",
            secure=True, HTTP_X_CSRFTOKEN=csrf,
        )
        return response

    def state(self, response):
        return parse_qs(urlsplit(response.json()["authorize_url"]).query)["state"][0]

    def callback(self, state, code="synthetic-auth-code"):
        return self.client.get(
            reverse("nuvemshop-oauth-callback"),
            {"state": state, "code": code}, secure=True,
        )

    def fake_token(self, store_id="999"):
        return {"access_token": "opaque-test-token-without-real-privileges",
                "store_id": store_id, "scope": "read_products"}

    def install(self, store_id="999"):
        self.assertEqual(self.start().status_code, 200)
        nonce = self.state(self.start()) if False else None  # Never start twice.
        # Start already produced the active attempt; load its hash only via URL.
        # Deliberately use a fresh start after clearing one-per-8s limiter.
        cache.clear()
        started = self.start()
        nonce = self.state(started)
        with patch("apps.nuvemshop.views.exchange_code", return_value=self.fake_token(store_id)):
            response = self.callback(nonce)
        return response

    def test_anonymous_and_cross_tenant_blocked(self):
        self.client.logout()
        response = self.client.post(self.start_url(), "{}", "application/json", secure=True)
        self.assertIn(response.status_code, (401, 403))
        self.client.force_login(self.foreign_user)
        response = self.start()
        self.assertEqual(response.status_code, 404)

    def test_start_requires_https_csrf_and_owner(self):
        csrf = self.client.cookies["csrftoken"].value
        self.assertEqual(self.client.post(
            self.start_url(), data="{}", content_type="application/json",
            secure=True
        ).status_code, 403)
        self.assertEqual(self.client.post(
            self.start_url(), data="{}", content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf
        ).status_code, 403)
        self.client.force_login(self.analyst)
        self.assertEqual(self.start().status_code, 403)

    def test_begin_and_callback_encrypt_token_and_no_leak(self):
        started = self.start()
        self.assertEqual(started.status_code, 200, started.content)
        url = started.json()["authorize_url"]
        self.assertTrue(url.startswith(
            "https://www.tiendanube.com/apps/12345/authorize?state="
        ))
        nonce = self.state(started)
        self.assertEqual(OAuthAttempt.objects.count(), 1)
        self.assertEqual(OAuthAttempt.objects.first().state_digest, digest(nonce))
        with patch("apps.nuvemshop.views.exchange_code", return_value=self.fake_token()) as mocked:
            result = self.callback(nonce)
        self.assertEqual(result.status_code, 303)
        self.assertEqual(result["Location"], "/?nuvemshop=connected")
        self.assertEqual(result["Referrer-Policy"], "no-referrer")
        self.assertNotIn(nonce, result["Location"])
        self.assertNotIn("synthetic-auth-code", result["Location"])
        mocked.assert_called_once()
        inst = NuvemshopInstallation.objects.get(tenant=self.tenant)
        self.assertEqual(inst.client_id, "12345")
        self.assertEqual(inst.store_id, "999")
        self.assertNotIn("opaque-test-token", inst.token_ciphertext)
        self.assertEqual(decrypt_token(inst.token_ciphertext, self.cipher_key),
                         "opaque-test-token-without-real-privileges")
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.external_store_id, "999")
        status = self.client.get(self.status_url(), secure=True)
        self.assertEqual(status.json()["store_id"], "999")
        self.assertEqual(status.json()["scope"], "read_products")
        self.assertNotIn("access_token", status.content.decode())

    def test_state_is_one_time_even_with_same_code(self):
        started = self.start()
        nonce = self.state(started)
        with patch("apps.nuvemshop.views.exchange_code", return_value=self.fake_token()) as exchange:
            self.assertEqual(self.callback(nonce).status_code, 303)
            self.assertEqual(self.callback(nonce)["Location"], "/?nuvemshop=failed")
        exchange.assert_called_once()
        self.assertEqual(NuvemshopInstallation.objects.count(), 1)

    def test_callback_wrong_session_or_expired_state(self):
        started = self.start()
        nonce = self.state(started)
        self.client.logout()
        self.client.force_login(self.owner)
        with patch("apps.nuvemshop.views.exchange_code") as exchange:
            self.assertEqual(self.callback(nonce)["Location"], "/?nuvemshop=failed")
        exchange.assert_not_called()
        self.assertFalse(NuvemshopInstallation.objects.exists())

        cache.clear()
        nonce2 = self.state(self.start())
        OAuthAttempt.objects.filter(state_digest=digest(nonce2)).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        with patch("apps.nuvemshop.views.exchange_code") as exchange:
            self.assertEqual(self.callback(nonce2)["Location"], "/?nuvemshop=failed")
        exchange.assert_not_called()

    def test_store_claimed_by_other_tenant_is_rejected(self):
        NuvemshopInstallation.objects.create(
            tenant=self.foreign, client_id="12345", store_id="999",
            scope="read_products",
            token_ciphertext=encrypt_token("foreign-opaque-synthetic", self.cipher_key),
        )
        self.foreign.external_store_id = "999"
        self.foreign.save(update_fields=["external_store_id"])
        nonce = self.state(self.start())
        with patch("apps.nuvemshop.views.exchange_code", return_value=self.fake_token()):
            self.assertEqual(self.callback(nonce)["Location"], "/?nuvemshop=failed")
        self.assertFalse(NuvemshopInstallation.objects.filter(tenant=self.tenant).exists())

    def test_configuration_missing_disables_connect(self):
        with patch.dict(os.environ, {"NUVEMSHOP_CLIENT_SECRET": ""}):
            response = self.start()
            self.assertEqual(response.status_code, 503)
            self.assertFalse(self.client.get(self.status_url(), secure=True).json()["configured"])

    def test_live_catalog_read_only_and_store_scoped(self):
        nonce = self.state(self.start())
        with patch("apps.nuvemshop.views.exchange_code", return_value=self.fake_token("999")):
            self.callback(nonce)
        item = CostItem.objects.create(
            tenant=self.tenant, name="Item manual", reference="MAN-1",
            sku="FITA", external_variant_id="333", unit_cost_cents=1000,
            selling_price_cents=2000,
        )
        products = [{"id": 111, "name": {"pt": "Fita teste"}, "variants": [{
            "id": 333, "sku": "FITA", "barcode": "07800001000",
            "price": "20.00", "promotional_price": None, "cost": None,
        }]}]
        with patch("apps.nuvemshop.views.read_products_page", return_value=products) as read:
            response = self.client.get(self.preview_url(), {"page": 1}, secure=True)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["source"], "nuvemshop_live_read_only")
        self.assertEqual(data["writes_performed"], 0)
        self.assertEqual(data["items"][0]["local_item_id"], str(item.pk))
        self.assertEqual(data["items"][0]["local_cost_cents"], 1000)
        self.assertIsNone(data["items"][0]["api_cost_cents"])
        self.assertEqual(read.call_args.kwargs["store_id"], 999)
        self.assertEqual(read.call_args.kwargs["per_page"], 3)
        item.refresh_from_db()
        self.assertEqual(item.unit_cost_cents, 1000)
        self.assertEqual(CostAudit.objects.count(), 0)
        self.assertEqual(self.client.get(self.preview_url(), secure=True).status_code, 429)

    def test_live_preview_never_uses_another_tenants_token(self):
        NuvemshopInstallation.objects.create(
            tenant=self.foreign, client_id="12345", store_id="700",
            scope="read_products",
            token_ciphertext=encrypt_token("foreign-opaque-synthetic", self.cipher_key),
        )
        self.foreign.external_store_id = "700"
        self.foreign.save(update_fields=["external_store_id"])
        with patch("apps.nuvemshop.views.read_products_page") as read:
            self.assertEqual(self.client.get(self.preview_url(), secure=True).status_code, 409)
            self.assertEqual(self.client.get(self.preview_url(self.foreign.pk), secure=True).status_code, 404)
        read.assert_not_called()
