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
from .merchant_auth import create_token, canonical_email
from .models import MerchantRegistration, MerchantPasswordReset, MerchantEmailIdentity, MerchantEmailClaim, EmailDispatch

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
        self.assertEqual(self.mock_mail.call_count, 1)
        args=self.mock_mail.call_args.args
        self.assertEqual(args[:2], ("register", str(pending.pk)))
        self.assertTrue(EmailDispatch.objects.filter(pk=args[2]).exists())
        self.assertEqual(get_user_model().objects.count(), 0)
        token = create_token("register", pending)
        result = self.post("merchant-confirm", {"token": token})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertTrue(result.json()["authenticated"])
        self.assertTrue(result.json()["store_linked"])
        user = get_user_model().objects.get()
        self.assertTrue(user.check_password(GOOD["password"]))
        self.assertFalse(user.is_staff)
        self.assertEqual(MerchantEmailIdentity.objects.get().normalized_email,
                         "lojista@example.invalid")
        self.assertEqual(MerchantEmailClaim.objects.get().canonical_email,
                         "lojista@example.invalid")
        tenant = Tenant.objects.get()
        self.assertIsNone(tenant.external_store_id)
        self.assertEqual(tenant.status, Tenant.Status.ACTIVE)
        self.assertEqual(tenant.platform, "independent")
        self.assertEqual(TenantMembership.objects.get(user=user).role, "owner")
        self.assertEqual(result.json()["store_id"], str(tenant.pk))
        session = self.client.get(reverse("auth-session")).json()
        self.assertTrue(session["authenticated"])
        self.assertEqual(len(session["tenants"]), 1)
        self.assertEqual(session["store_link_status"], "linked")
        self.csrf = self.client.cookies["csrftoken"].value
        self.assertEqual(self.post("merchant-confirm", {"token": token}).status_code, 400)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), 1)

    def test_confirmation_rolls_back_user_and_store_when_membership_fails(self):
        from django.db import IntegrityError

        self.assertEqual(self.register().status_code, 202)
        pending = MerchantRegistration.objects.get()
        token = create_token("register", pending)
        with patch(
            "apps.core.merchant_auth_views.TenantMembership.objects.create",
            side_effect=IntegrityError("synthetic error"),
        ):
            response = self.post("merchant-confirm", {"token": token})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Tenant.objects.exists())
        self.assertFalse(TenantMembership.objects.exists())
        self.assertFalse(MerchantEmailIdentity.objects.exists())
        self.assertFalse(MerchantEmailClaim.objects.exists())
        pending.refresh_from_db()
        self.assertIsNone(pending.consumed_at)
        self.assertNotEqual(pending.password_hash, "!")
        # Uma nova confirmação válida cria exatamente uma loja e seu dono.
        recovered = self.post("merchant-confirm", {"token": token})
        self.assertEqual(recovered.status_code, 200)
        self.assertTrue(recovered.json()["store_linked"])
        self.assertEqual(TenantMembership.objects.count(), 1)

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
        self.assertEqual(self.mock_mail.call_count, 1)
        args=self.mock_mail.call_args.args
        self.assertEqual(args[:2], ("register", str(row.pk)))
        self.assertTrue(EmailDispatch.objects.filter(pk=args[2]).exists())

    def test_resend_from_canonical_gmail_alias_uses_original_address(self):
        self.assertEqual(self.post("merchant-register", {
            **GOOD,"email":"pessoa.teste+cadastro@gmail.com",
        }).status_code,202)
        pending=MerchantRegistration.objects.get()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.post("merchant-resend", {
                "email":"pessoateste@googlemail.com",
            }).status_code,202)
        self.assertEqual(self.mock_mail.call_count,1)
        args=self.mock_mail.call_args.args
        self.assertEqual(args[:2],("register",str(pending.pk)))
        self.assertTrue(EmailDispatch.objects.filter(pk=args[2]).exists())
        self.assertEqual(EmailDispatch.objects.count(),2)
        self.assertEqual(MerchantRegistration.objects.count(),1)

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
        self.assertEqual(self.mock_mail.call_count, 1)
        args=self.mock_mail.call_args.args
        self.assertEqual(args[:2], ("reset", str(reset.pk)))
        self.assertTrue(EmailDispatch.objects.filter(pk=args[2]).exists())
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

    def test_signup_does_not_require_nuvemshop_or_create_duplicate_tenants(self):
        self.assertEqual(self.register().status_code, 202)
        pending=MerchantRegistration.objects.get()
        self.assertFalse(Tenant.objects.exists())
        self.assertEqual(
            self.post("merchant-confirm", {"token":create_token("register",pending)}).status_code,
            200,
        )
        self.assertEqual(Tenant.objects.get().platform, "independent")
        self.csrf=self.client.cookies["csrftoken"].value
        # Tentar cadastrar novamente a mesma caixa não cria outra loja/conta.
        self.assertEqual(self.register().status_code, 202)
        self.assertEqual(Tenant.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_gmail_alias_cannot_register_second_account(self):
        first = {**GOOD, "email": "minha.loja+um@gmail.com"}
        self.assertEqual(self.post("merchant-register", first).status_code, 202)
        pending = MerchantRegistration.objects.get()
        token = create_token("register", pending)
        self.assertEqual(self.post("merchant-confirm", {"token":token}).status_code, 200)
        self.assertEqual(MerchantEmailClaim.objects.get().canonical_email,
                         "minhaloja@gmail.com")
        self.csrf = self.client.cookies["csrftoken"].value
        second = {**GOOD, "email": "minhaloja+dois@googlemail.com"}
        self.assertEqual(self.post("merchant-register", second).status_code, 202)
        self.assertEqual(MerchantRegistration.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), 1)
        self.assertEqual(canonical_email("minha.loja+uma@gmail.com"),
                         "minhaloja@gmail.com")
        self.assertEqual(canonical_email("nome+segundo@outro.com"),
                         "nome+segundo@outro.com")

    def test_two_pending_gmail_aliases_cannot_confirm_both(self):
        one = MerchantRegistration.objects.create(
            normalized_email="loja.um+um@gmail.com", first_name="Loja",
            store_name="Um", password_hash="hashed", expires_at=timezone.now()+timedelta(minutes=30))
        two = MerchantRegistration.objects.create(
            normalized_email="lojaum+dois@googlemail.com", first_name="Loja",
            store_name="Dois", password_hash="hashed", expires_at=timezone.now()+timedelta(minutes=30))
        self.assertEqual(self.post("merchant-confirm", {"token":create_token("register", one)}).status_code, 200)
        self.csrf=self.client.cookies["csrftoken"].value
        self.assertEqual(self.post("merchant-confirm", {"token":create_token("register", two)}).status_code, 409)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), 1)

    def test_duplicate_legacy_email_blocks_signup_even_if_ambiguous(self):
        User=get_user_model()
        User.objects.create_user(username="legacy1", email="antigo@example.invalid", password="senha-1")
        User.objects.create_user(username="legacy2", email="antigo@example.invalid", password="senha-2")
        self.assertEqual(self.post("merchant-register", {
            **GOOD, "email":"antigo@example.invalid"
        }).status_code, 202)
        self.assertEqual(MerchantRegistration.objects.count(), 0)

    def test_gmail_alias_login_and_password_reset_target_verified_address(self):
        self.assertEqual(self.post("merchant-register", {
            **GOOD,"email":"nome.sobrenome@gmail.com"
        }).status_code,202)
        pending=MerchantRegistration.objects.get()
        self.assertEqual(self.post("merchant-confirm", {"token":create_token("register",pending)}).status_code,200)
        self.csrf=self.client.cookies["csrftoken"].value
        self.assertEqual(self.post("auth-login",{
            "email":"nomesobrenome+promo@googlemail.com",
            "password":GOOD["password"],
        }).status_code,200)
        # Login Django roda rotate_token(): sempre ler CSRF atualizado.
        self.csrf=self.client.cookies["csrftoken"].value
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.post("merchant-reset-request", {
                "email":"nomesobrenome+recuperacao@gmail.com"
            }).status_code,202)
        self.assertEqual(MerchantPasswordReset.objects.get().email_snapshot,
                         "nome.sobrenome@gmail.com")

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

    def test_registration_audit_is_readonly_masked_and_superuser_only(self):
        from django.contrib.auth import get_user_model
        from apps.core.models import MerchantRegistration
        from datetime import timedelta
        from django.utils import timezone
        url=reverse("admin:core_merchantregistration_changelist")
        item=MerchantRegistration.objects.create(
            normalized_email="teste.sigiloso@example.invalid",
            first_name="Pessoa", store_name="Loja auditável",
            password_hash="SECRET_PASSWORD_HASH_MUST_NEVER_APPEAR",
            expires_at=timezone.now()+timedelta(minutes=30),
        )
        self.assertEqual(self.client.get(url).status_code, 302)
        merchant=get_user_model().objects.create_user(
            username="lojista", email="lojista@example.invalid",
            password="SenhaSeguraTeste#2026",
        )
        self.client.force_login(merchant)
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.logout()
        operator=get_user_model().objects.create_superuser(
            username="adm-qa", email="admin@example.invalid",
            password="SenhaForte#2026admin",
        )
        self.client.force_login(operator)
        response=self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Loja auditável")
        self.assertContains(response, "Aguardando confirmação")
        self.assertNotContains(response, "SECRET_PASSWORD_HASH_MUST_NEVER_APPEAR")
        self.assertNotContains(response, "teste.sigiloso@example.invalid")
        self.assertEqual(
            self.client.get(reverse("admin:core_merchantregistration_change",
                                    args=[item.pk])).status_code,200
        )
        self.assertEqual(
            self.client.post(reverse("admin:core_merchantregistration_change",
                                     args=[item.pk]), {}).status_code,403
        )

    def test_admin_is_registered_and_requires_admin_login(self):
        self.assertEqual(reverse("admin:index"), "/admin/")
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
        login_response = self.client.get("/admin/login/")
        self.assertEqual(login_response.status_code, 200)
