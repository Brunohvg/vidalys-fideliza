"""Teste integral do cadastro dos lojistas: nunca envia email externo."""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.tenants.models import Tenant, TenantMembership
from .merchant_auth import create_token
from .models import MerchantRegistration, MerchantPasswordReset, MerchantEmailIdentity

EMAIL_SETTINGS = {
    "FIDELIZA_MERCHANT_SIGNUP_ENABLED": True,
    "FIDELIZA_EMAIL_DELIVERY_ENABLED": True,
    "FIDELIZA_PUBLIC_BASE_URL": "https://fideliza-homolog.optarys.com.br",
}
GOOD = {
    "name": "Lojista Teste",
    "email": " LoJisTa@Example.invalid ",
    "store_name": "Armarinho de Testes",
    "password": "SenhaForte-2026-sem-reuso!",
}


@override_settings(**EMAIL_SETTINGS)
class MerchantAuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.client.get(reverse("auth-session"))
        self.csrf = self.client.cookies["csrftoken"].value
        self.sent = patch("apps.core.tasks.send_merchant_auth_email.delay")
        self.mock_mail = self.sent.start()
        self.addCleanup(self.sent.stop)

    def post(self, name, payload, csrf=True):
        return self.client.post(reverse(name), data=json.dumps(payload),
                                content_type="application/json",
                                **({"HTTP_X_CSRFTOKEN": self.csrf} if csrf else {}))

    def register(self):
        return self.post("merchant-register", GOOD)

    def test_registration_requires_csrf_and_mail_and_flag(self):
        self.assertEqual(self.post("merchant-register", GOOD, False).status_code, 403)
        with override_settings(FIDELIZA_MERCHANT_SIGNUP_ENABLED=False):
            self.assertEqual(self.register().status_code, 503)
        with override_settings(FIDELIZA_EMAIL_DELIVERY_ENABLED=False):
            self.assertEqual(self.register().status_code, 503)
        self.assertFalse(MerchantRegistration.objects.exists())
        self.mock_mail.assert_not_called()

    def test_signup_confirmation_creates_tenant_owner_and_login_without_nuvemshop(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.register().status_code, 202)
        pending = MerchantRegistration.objects.get()
        self.assertEqual(pending.normalized_email, "lojista@example.invalid")
        self.assertNotIn(GOOD["password"], pending.password_hash)
        self.mock_mail.assert_called_once_with("register", str(pending.pk))
        self.assertEqual(get_user_model().objects.count(), 0)
        token = create_token("register", pending)
        result = self.post("merchant-confirm", {"token": token})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertTrue(result.json()["authenticated"])
        user = get_user_model().objects.get()
        self.assertTrue(user.check_password(GOOD["password"]))
        self.assertFalse(user.is_staff)
        self.assertEqual(MerchantEmailIdentity.objects.get().normalized_email,
                         "lojista@example.invalid")
        tenant = Tenant.objects.get()
        self.assertIsNone(tenant.external_store_id)
        self.assertEqual(tenant.status, Tenant.Status.ACTIVE)
        self.assertEqual(TenantMembership.objects.get(user=user).role, "owner")
        session = self.client.get(reverse("auth-session")).json()
        self.assertTrue(session["authenticated"])
        self.assertEqual(len(session["tenants"]), 1)
        self.csrf = self.client.cookies["csrftoken"].value
        self.assertEqual(self.post("merchant-confirm", {"token": token}).status_code, 400)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), 1)

    def test_registration_validation_throttle_duplicates_and_expiration(self):
        bad = {**GOOD, "password": "123"}
        self.assertEqual(self.post("merchant-register", bad).status_code, 400)
        self.assertEqual(self.register().status_code, 202)
        self.assertEqual(self.register().status_code, 202)
        self.assertEqual(MerchantRegistration.objects.count(), 1)
        row = MerchantRegistration.objects.get()
        old_token = create_token("register", row)
        MerchantRegistration.objects.filter(pk=row.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post("merchant-confirm", {"token": old_token}).status_code, 400)

    def test_resend_is_generic_and_throttled(self):
        self.assertEqual(self.post("merchant-resend", {"email": "nobody@example.invalid"}).status_code, 202)
        self.register()
        row = MerchantRegistration.objects.get()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.post("merchant-resend", {"email": row.normalized_email}).status_code, 202)
        self.mock_mail.assert_called_once_with("register", str(row.pk))

    def test_password_reset_generic_replay_and_login_with_email(self):
        user = get_user_model().objects.create_user(
            username="merchant-internal", email="lojista@example.invalid",
            password="SenhaAntiga-2026-ok!")
        MerchantEmailIdentity.objects.create(
            user=user, normalized_email="lojista@example.invalid",
            verified_at=timezone.now())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.post("merchant-reset-request", {
                "email": "LOJISTA@EXAMPLE.INVALID"
            }).status_code, 202)
        reset = MerchantPasswordReset.objects.get()
        self.mock_mail.assert_called_once_with("reset", str(reset.pk))
        token = create_token("reset", reset)
        self.assertEqual(self.post("merchant-reset-confirm", {
            "token": token, "password": "SenhaNova-2026-supersegura!"
        }).status_code, 200)
        self.assertEqual(self.post("merchant-reset-confirm", {
            "token": token, "password": "SenhaNova-2026-supersegura!"
        }).status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password("SenhaNova-2026-supersegura!"))
        self.assertEqual(self.post("auth-login", {
            "email": "LOJISTA@example.invalid", "password": "SenhaNova-2026-supersegura!"
        }).status_code, 200)

    def test_password_reset_unknown_email_never_discloses_account(self):
        self.assertEqual(self.post("merchant-reset-request", {
            "email": "unknown@example.invalid"
        }).status_code, 202)
        self.assertFalse(MerchantPasswordReset.objects.exists())
        self.mock_mail.assert_not_called()

    def test_only_one_identity_per_email_and_csrf_on_confirm(self):
        self.register()
        row = MerchantRegistration.objects.get()
        token = create_token("register", row)
        self.assertEqual(self.post("merchant-confirm", {"token": token}, csrf=False).status_code, 403)
        self.assertEqual(self.post("merchant-confirm", {"token": "bad"}).status_code, 400)
        self.assertEqual(self.post("merchant-confirm", {"token": token}).status_code, 200)
        self.client.get(reverse("auth-session"))
        self.csrf = self.client.cookies["csrftoken"].value
        self.assertEqual(self.register().status_code, 202)
        self.assertEqual(get_user_model().objects.count(), 1)


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class DjangoAdminRoutingTests(TestCase):
    def test_admin_is_registered_and_requires_admin_login(self):
        self.assertEqual(reverse("admin:index"), "/admin/")
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
        login_response = self.client.get("/admin/login/")
        self.assertEqual(login_response.status_code, 200)
