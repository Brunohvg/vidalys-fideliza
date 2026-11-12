"""Segurança, acessibilidade e compatibilidade dos e-mails transacionais."""
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta

from apps.core.email_templates import transactional_message
from apps.core.merchant_auth import create_token
from apps.core.models import MerchantRegistration, MerchantPasswordReset
from apps.core.tasks import send_merchant_auth_email


@override_settings(
    FIDELIZA_PUBLIC_BASE_URL="https://fideliza-homolog.optarys.com.br",
)
class TransactionalEmailTemplateTests(TestCase):
    def test_brand_safe_html_and_plain_fallback(self):
        plain, html = transactional_message(
            title="Confirme & avance",
            greeting="Olá, <script>alert(1)</script>!",
            description='Loja "A & B" <imagem>',
            action_label="Confirmar acesso",
            action_url="https://fideliza-homolog.optarys.com.br/confirmar-conta#token=abc",
            context="Cadastro do lojista",
            safety_note="Link válido por 30 minutos.",
            footer_note="Não gera benefícios.",
        )
        self.assertIn("Confirme & avance", plain)
        self.assertIn("Loja &quot;A &amp; B&quot; &lt;imagem&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('lang="pt-BR"', html)
        self.assertIn("Vidalys Fideliza", html)
        self.assertIn("/email-assets/vidalys-fideliza-logo.png", html)
        self.assertIn('href="https://fideliza-homolog.optarys.com.br/', html)
        self.assertIn("background:#087f79", html)
        self.assertIn("Confirmar acesso", plain)

    @override_settings(
        FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="smtp.invalid", EMAIL_HOST_USER="qa", EMAIL_HOST_PASSWORD="synthetic",
        DEFAULT_FROM_EMAIL="Vidalys Fideliza <qa@example.invalid>",
        EMAIL_USE_TLS=True, EMAIL_USE_SSL=False,
    )
    @patch("apps.core.tasks._smtp_ready", return_value=True)
    def test_registration_email_has_real_html_alternative(self, _ready):
        pending = MerchantRegistration.objects.create(
            normalized_email="teste@example.invalid", first_name="Teste <Pessoa>",
            store_name="Loja <A & B>", password_hash="hashed",
            expires_at=timezone.now()+timedelta(minutes=30),
        )
        self.assertEqual(send_merchant_auth_email.run("register", str(pending.pk)), "sent")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("Confirme seu e-mail", message.subject)
        self.assertIn("Confirmar meu e-mail", message.body)
        self.assertEqual(len(message.alternatives), 1)
        html = message.alternatives[0][0]
        self.assertIn("&lt;Pessoa&gt;", html)
        self.assertIn("Loja &lt;A &amp; B&gt;", html)
        self.assertNotIn("Loja <A & B>", html)
        self.assertIn("vidalys-fideliza-logo.png", html)
        self.assertIn("#token=", message.body)

    @override_settings(
        FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="smtp.invalid", EMAIL_HOST_USER="qa", EMAIL_HOST_PASSWORD="synthetic",
        DEFAULT_FROM_EMAIL="Vidalys Fideliza <qa@example.invalid>",
        EMAIL_USE_TLS=True, EMAIL_USE_SSL=False,
    )
    @patch("apps.core.tasks._smtp_ready", return_value=True)
    def test_password_reset_email_has_security_copy(self, _ready):
        from django.contrib.auth import get_user_model
        user=get_user_model().objects.create_user(
            username="qaflow",email="qa@example.invalid",password="SenhaAntigaDeTeste#2026")
        reset=MerchantPasswordReset.objects.create(
            user=user,email_snapshot="qa@example.invalid",
            expires_at=timezone.now()+timedelta(minutes=30))
        self.assertEqual(send_merchant_auth_email.run("reset", str(reset.pk)), "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Redefina sua senha", mail.outbox[0].subject)
        self.assertIn("Criar nova senha", mail.outbox[0].body)
        self.assertIn("Sua senha atual permanecerá válida", mail.outbox[0].body)
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
