"""Prévia Nuvemshop read_customers: nunca gravar participante nem navegar por PII arbitrária."""
from unittest.mock import patch
import io
import json

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.nuvemshop.customer_lookup import exact_email_match, read_customer_candidates
from apps.nuvemshop.provider import exchange_code, OAuthExchangeError
from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.scopes import allowed_scopes, has_customer_access
from apps.nuvemshop.security import OAuthConfig
from apps.tenants.models import Tenant, TenantMembership
from .enrollment_models import EnrollmentInvite, EnrollmentSubmission, ProgramTerms
from .models import ProgramParticipant


class ScopeContractTests(TestCase):
    def test_only_explicit_read_only_scopes(self):
        self.assertTrue(allowed_scopes("read_products", customer_preview_enabled=False))
        self.assertFalse(allowed_scopes("read_products,read_customers",
                                        customer_preview_enabled=False))
        self.assertTrue(allowed_scopes("read_products,read_customers",
                                       customer_preview_enabled=True))
        for scope in ("write_customers", "write_orders", "read_orders",
                      "read_customers", "read_products,write_products",
                      "read_products,read_customers,write_customers"):
            with self.subTest(scope=scope):
                self.assertFalse(allowed_scopes(scope, customer_preview_enabled=True))
        self.assertFalse(has_customer_access("read_products", customer_preview_enabled=True))

    def test_oauth_expansion_requires_explicit_flag_and_reinstallation(self):
        class OAuthAnswer:
            def __init__(self, scopes):
                self.scopes = scopes
            def open(self, req, timeout):
                return io.BytesIO(json.dumps({
                    "access_token": "x" * 48,
                    "token_type": "bearer", "user_id": 1234,
                    "scope": self.scopes,
                }).encode())
        with override_settings(FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=False):
            with self.assertRaises(OAuthExchangeError):
                exchange_code("secure-code-123", "11111", "test-client-secret",
                              opener=OAuthAnswer("read_products,read_customers"))
        with override_settings(FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=True):
            result = exchange_code("secure-code-123", "11111", "test-client-secret",
                                   opener=OAuthAnswer("read_customers,read_products"))
            self.assertEqual(result["scope"], "read_customers,read_products")
            with self.assertRaises(OAuthExchangeError):
                exchange_code("secure-code-123", "11111", "test-client-secret",
                              opener=OAuthAnswer("read_customers,read_products,write_orders"))

    def test_http_reads_minimum_customer_fields(self):
        class Capture:
            def open(self, request, timeout):
                self.url = request.full_url
                self.authorization = request.get_header("Authorization")
                self.user_agent = request.get_header("User-agent")
                self.timeout = timeout
                return io.BytesIO(json.dumps([
                    {"id": 1234, "email": "CLIENTE@example.invalid", "phone": "NAO REPLICAR"},
                    {"id": 1235, "email": "unrelated@example.invalid"}
                ]).encode())
        transport = Capture()
        rows = read_customer_candidates(
            store_id=123, access_token="a" * 32,
            user_agent="Vidalys Fideliza (contato@vidalys.com.br)",
            email="cliente@example.invalid", opener=transport,
        )
        self.assertIn("/2025-03/123/customers?", transport.url)
        self.assertIn("email=cliente%40example.invalid", transport.url)
        self.assertIn("fields=id%2Cemail", transport.url)
        self.assertEqual(transport.authorization, "Bearer " + "a"*32)
        self.assertEqual(transport.timeout, 8)
        self.assertEqual(set(rows[0]), {"id", "email"})
        self.assertEqual(exact_email_match(rows, "CLIENTE@example.invalid"),
                         ("one_exact_match", "1234"))
        self.assertEqual(exact_email_match(rows, "none@example.invalid"),
                         ("not_found", None))
        self.assertEqual(exact_email_match([rows[0], rows[0], {"id": "9", "email": rows[0]["email"]}],
                                           "CLIENTE@example.invalid"),
                         ("ambiguous", None))


@override_settings(FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=True)
class CustomerLinkPreviewTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.owner = User.objects.create_user(username="scope-owner")
        self.analyst = User.objects.create_user(username="scope-analyst")
        self.outsider = User.objects.create_user(username="scope-outsider")
        self.tenant = Tenant.objects.create(
            name="Loja teste vínculo", slug="scope-loja", status="active",
            external_store_id="1234",
        )
        self.other = Tenant.objects.create(
            name="Outra loja", slug="scope-outra", status="active",
            external_store_id="9876",
        )
        for user, tenant, role in [
            (self.owner, self.tenant, "owner"),
            (self.analyst, self.tenant, "analyst"),
            (self.outsider, self.other, "owner"),
        ]:
            TenantMembership.objects.create(tenant=tenant, user=user, role=role)
        self.terms = ProgramTerms.objects.create(
            tenant=self.tenant, version="v1", title="Termos de participação",
            body="Regulamento de testes: sem concessão automática de cashback. "*3,
            privacy_notice="Texto para testes de privacidade e direitos do usuário. "*3,
            approved_at=timezone.now(),
        )
        invite = EnrollmentInvite.objects.create(
            tenant=self.tenant, terms=self.terms, token_digest="c"*64,
            expires_at=timezone.now(), consumed_at=timezone.now(),
        )
        self.submission = EnrollmentSubmission.objects.create(
            tenant=self.tenant, invitation=invite, terms=self.terms,
            name="Cliente de teste", email="cliente@example.invalid",
            terms_digest="a"*64, accepted_at=timezone.now(),
            email_verified_at=timezone.now(), status="email_verified",
        )
        self.cfg=OAuthConfig(
            client_id="11111",client_secret="secret",callback_url="https://example.invalid/callback",
            user_agent="Vidalys Fideliza (contato@vidalys.com.br)",token_keys="dummy",
        )
        self.install = NuvemshopInstallation.objects.create(
            tenant=self.tenant, client_id="11111", store_id="1234",
            token_ciphertext="opaque-for-tests",
            scope="read_customers,read_products",
        )
        self.client=APIClient()
        self.client.force_authenticate(self.owner)

    def url(self, tenant_id=None, submission_id=None):
        return reverse("tenant-customer-match-preview", kwargs={
            "tenant_id": tenant_id or self.tenant.id,
            "submission_id": submission_id or self.submission.id,
        })

    def test_verified_exact_customer_read_only_preview(self):
        with patch("apps.participants.customer_link_preview.config", return_value=self.cfg), \
             patch("apps.participants.customer_link_preview.decrypt_token",
                   return_value="a"*32), \
             patch("apps.participants.customer_link_preview.read_customer_candidates",
                   return_value=[
                       {"id":"123","email":"cliente@example.invalid"},
                       {"id":"456","email":"not-the-same@example.invalid"},
                   ]) as read:
            response=self.client.post(self.url(), {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "one_exact_match")
        self.assertEqual(response.data["customer_id"], "123")
        self.assertEqual(response.data["writes_performed"], 0)
        self.assertFalse(response.data["participant_created"])
        self.assertFalse(response.data["cashback_enabled"])
        self.assertEqual(ProgramParticipant.objects.count(), 0)
        self.assertEqual(read.call_args.kwargs["email"], self.submission.email)
        self.assertEqual(read.call_args.kwargs["store_id"], 1234)
        self.assertEqual(self.client.post(self.url(), {}, format="json").status_code, 429)

    def test_unverified_and_withdrawn_are_never_queried(self):
        with patch("apps.participants.customer_link_preview.read_customer_candidates") as read:
            self.submission.status="pending_verification"
            self.submission.email_verified_at=None
            self.submission.save(update_fields=["status","email_verified_at"])
            self.assertEqual(self.client.post(self.url(), {},format="json").status_code,409)
            self.submission.status="withdrawn"
            self.submission.withdrawn_at=timezone.now()
            self.submission.save(update_fields=["status","withdrawn_at"])
            self.assertEqual(self.client.post(self.url(), {},format="json").status_code,409)
        read.assert_not_called()

    def test_tenant_isolation_roles_and_payload(self):
        self.assertEqual(self.client.post(self.url(),{"email":"attacker@example.invalid"},
                                          format="json").status_code,400)
        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.post(self.url(),{},format="json").status_code,403)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.post(self.url(),{},format="json").status_code,404)
        self.client.force_authenticate(None)
        self.assertIn(self.client.post(self.url(),{},format="json").status_code,(401,403))

    def test_missing_scope_or_other_store_blocks_api(self):
        self.install.scope="read_products"
        self.install.save(update_fields=["scope"])
        with patch("apps.participants.customer_link_preview.read_customer_candidates") as read:
            self.assertEqual(self.client.post(self.url(),{},format="json").status_code,409)
            self.install.scope="read_customers,read_products"
            self.install.store_id="99"
            self.install.save(update_fields=["scope","store_id"])
            self.assertEqual(self.client.post(self.url(),{},format="json").status_code,409)
        read.assert_not_called()

    def test_feature_gate_off_even_if_scope_present(self):
        with override_settings(FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED=False):
            self.assertEqual(self.client.post(self.url(),{},format="json").status_code,409)

    def test_ambiguous_email_never_selects_customer(self):
        with patch("apps.participants.customer_link_preview.config", return_value=self.cfg), \
             patch("apps.participants.customer_link_preview.decrypt_token",
                   return_value="a"*32), \
             patch("apps.participants.customer_link_preview.read_customer_candidates",
                   return_value=[
                       {"id":"123","email":"cliente@example.invalid"},
                       {"id":"456","email":"cliente@example.invalid"},
                   ]):
            response=self.client.post(self.url(),{},format="json")
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["status"],"ambiguous")
        self.assertIsNone(response.data["customer_id"])
        self.assertFalse(ProgramParticipant.objects.exists())
