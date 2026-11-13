"""Ações administrativas de inscrições, sem SMTP real nem exclusão de lojas."""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.tenants.models import Tenant, TenantMembership
from .merchant_auth import create_token
from .models import MerchantRegistration, MerchantEmailIdentity


@override_settings(
    FIDELIZA_MERCHANT_SIGNUP_ENABLED=True,
    FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
    FIDELIZA_PUBLIC_BASE_URL="https://fideliza-homolog.optarys.com.br",
)
class RegistrationModerationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.api = Client(enforce_csrf_checks=True)
        self.api.get(reverse("auth-session"))
        self.csrf = self.api.cookies["csrftoken"].value
        self.admin_user = get_user_model().objects.create_superuser(
            username="moderator-test", email="moderator@example.invalid",
            password="synthetic-moderation-2026",
        )
        self.admin = Client()
        self.admin.force_login(self.admin_user)
        self.url = reverse("admin:core_merchantregistration_changelist")
        self.sender = patch("apps.core.tasks.send_merchant_auth_email.delay")
        self.mock_mail = self.sender.start()
        self.addCleanup(self.sender.stop)

    def post(self, name, body):
        return self.api.post(
            reverse(name),
            data=json.dumps(body), content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )

    def register(self, email="one@example.invalid"):
        return self.post("merchant-register", {
            "name":"Lojista de Teste", "store_name":"Empresa de Teste",
            "email":email, "password":"SenhaTesteForte-2026-!",
        })

    def action(self, action, *ids):
        return self.admin.post(self.url, {
            "action":action, "_selected_action":[str(i) for i in ids],
        })

    def test_cancel_invalidates_link_and_can_register_again(self):
        self.assertEqual(self.register().status_code, 202)
        obj = MerchantRegistration.objects.get()
        token = create_token("register", obj)
        self.assertEqual(self.action("cancel_pending", obj.pk).status_code, 302)
        obj.refresh_from_db()
        self.assertIsNotNone(obj.cancelled_at)
        self.assertEqual(obj.password_hash, "!")
        self.assertEqual(
            self.post("merchant-confirm", {"token":token}).status_code, 400
        )
        before = self.mock_mail.call_count
        self.post("merchant-resend", {"email":obj.normalized_email})
        self.assertEqual(self.mock_mail.call_count, before)
        cache.clear()
        self.assertEqual(self.register().status_code, 202)
        current = MerchantRegistration.objects.get()
        self.assertNotEqual(current.pk, obj.pk)
        self.assertFalse(Tenant.objects.exists())

    def test_block_prevents_new_registration_with_gmail_alias_and_unblock_releases(self):
        self.register("pessoa.teste+primeiro@gmail.com")
        obj = MerchantRegistration.objects.get()
        token = create_token("register", obj)
        self.assertEqual(self.action("block_pending", obj.pk).status_code, 302)
        obj.refresh_from_db()
        self.assertIsNotNone(obj.blocked_at)
        self.assertEqual(self.post("merchant-confirm", {"token":token}).status_code, 400)
        cache.clear()
        self.assertEqual(self.register("pessoateste+outro@googlemail.com").status_code, 202)
        self.assertEqual(MerchantRegistration.objects.count(), 1)
        self.assertEqual(self.mock_mail.call_count, 0)
        self.assertEqual(self.action("unblock_pending", obj.pk).status_code, 302)
        cache.clear()
        self.assertEqual(self.register("pessoa.teste+primeiro@gmail.com").status_code, 202)
        current = MerchantRegistration.objects.get()
        self.assertNotEqual(current.pk, obj.pk)
        self.assertIsNone(current.blocked_at)

    def test_delete_only_unconfirmed_unblocked_and_reject_direct_deletion(self):
        self.register("pending@example.invalid")
        pending = MerchantRegistration.objects.get()
        cache.clear()
        self.register("confirmed@example.invalid")
        confirmed = MerchantRegistration.objects.get(normalized_email="confirmed@example.invalid")
        self.assertEqual(
            self.post("merchant-confirm", {"token":create_token("register",confirmed)}).status_code,200
        )
        self.assertEqual(self.action("delete_pending", pending.pk,confirmed.pk).status_code,302)
        self.assertFalse(MerchantRegistration.objects.filter(pk=pending.pk).exists())
        self.assertTrue(MerchantRegistration.objects.filter(pk=confirmed.pk).exists())
        self.assertEqual(Tenant.objects.count(), 1)
        self.assertEqual(TenantMembership.objects.count(), 1)
        self.assertEqual(self.admin.get(
            reverse("admin:core_merchantregistration_delete",args=[confirmed.pk]),
        ).status_code,403)

    def test_confirmed_account_can_be_blocked_and_restored_without_deleting_tenant(self):
        self.register("active@example.invalid")
        obj = MerchantRegistration.objects.get()
        confirm = self.post("merchant-confirm", {"token":create_token("register",obj)})
        self.assertEqual(confirm.status_code,200)
        user = MerchantEmailIdentity.objects.get(normalized_email="active@example.invalid").user
        self.assertTrue(user.is_active)
        self.assertEqual(self.action("cancel_pending",obj.pk).status_code,302)
        self.assertIsNone(MerchantRegistration.objects.get(pk=obj.pk).cancelled_at)
        self.assertEqual(self.action("block_confirmed",obj.pk).status_code,302)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(self.api.get(reverse("auth-session")).json()["authenticated"],False)
        self.assertEqual(Tenant.objects.count(),1)
        self.assertEqual(TenantMembership.objects.count(),1)
        self.assertEqual(self.action("unblock_confirmed",obj.pk).status_code,302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertIsNone(MerchantRegistration.objects.get(pk=obj.pk).blocked_at)
        self.assertEqual(Tenant.objects.count(),1)

    def test_only_superuser_can_moderate(self):
        self.register()
        obj = MerchantRegistration.objects.get()
        ordinary=get_user_model().objects.create_user(
            username="ordinary",password="synthetic-2026",is_staff=True,
        )
        self.admin.force_login(ordinary)
        self.assertIn(self.action("block_pending",obj.pk).status_code,(302,403))
        obj.refresh_from_db()
        self.assertIsNone(obj.blocked_at)
