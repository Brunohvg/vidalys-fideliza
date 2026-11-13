"""Testes de comprovação de e-mail e retirada sem participantes ou cashback."""
import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from .email_proof import consume_challenge, digest, email_delivery_ready, enqueue_confirmation, make_token
from .enrollment_models import (
    EnrollmentEmailChallenge, EnrollmentInvite, EnrollmentSubmission, ProgramTerms,
)
from .models import ProgramParticipant
from apps.core.models import EmailDispatch


@override_settings(
    FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
    FIDELIZA_PUBLIC_BASE_URL="https://fideliza-homolog.optarys.com.br",
)
class EmailProofTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja de testes", slug="loja-mail-seguro", status=Tenant.Status.ACTIVE,
        )
        self.terms = ProgramTerms.objects.create(
            tenant=self.tenant, version="v1",
            title="Regulamento teste",
            body="Regulamento de teste com aceitação expressa e registro sem cashback. " * 3,
            privacy_notice="Aviso de privacidade de teste e não aplicável em produção. " * 3,
            approved_at=timezone.now(), active=True,
        )
        self.invite = EnrollmentInvite.objects.create(
            tenant=self.tenant, terms=self.terms,
            token_digest="a" * 64, expires_at=timezone.now() + timedelta(hours=1),
            consumed_at=timezone.now(),
        )
        self.submission = EnrollmentSubmission.objects.create(
            tenant=self.tenant, terms=self.terms, invitation=self.invite,
            name="Cliente teste", email="teste@example.invalid",
            terms_digest="b" * 64, accepted_at=timezone.now(),
            marketing_opt_in=True,
        )
        self.client = APIClient()

    def issue(self, purpose):
        with patch("apps.participants.tasks.send_enrollment_email.delay") as delayed:
            with self.captureOnCommitCallbacks(execute=True):
                result = enqueue_confirmation(self.submission, purpose)
            self.assertTrue(result)
            self.assertEqual(delayed.call_count, 1)
            challenge = EnrollmentEmailChallenge.objects.get(purpose=purpose)
            cid,event_id = delayed.call_args.args
            self.assertEqual(cid, str(challenge.pk))
            self.assertEqual(str(EmailDispatch.objects.get().pk),event_id)
            token = make_token(challenge.pk, purpose)
            self.assertEqual(challenge.token_digest, digest(token))
            self.assertNotEqual(token, challenge.token_digest)
        return challenge, token


    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Vidalys Fideliza <qa@example.invalid>",
    )
    @patch("apps.participants.tasks.email_delivery_ready", return_value=True)
    def test_participant_email_has_safe_html_and_text(self, _ready):
        from .tasks import send_enrollment_email
        challenge, token = self.issue("verify")
        self.assertEqual(send_enrollment_email.run(str(challenge.pk)), "sent")
        self.assertEqual(len(mail.outbox), 1)
        message=mail.outbox[0]
        self.assertIn(self.tenant.name, message.subject)
        self.assertIn("Confirmar meu e-mail", message.body)
        self.assertIn(token, message.body)
        self.assertEqual(len(message.alternatives), 1)
        html=message.alternatives[0][0]
        self.assertIn("vidalys-fideliza-logo.png", html)
        self.assertNotIn("Nuvemshop", html)  # Canal opcional, não exigir integração
        self.assertNotIn("<script", html)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Vidalys Fideliza <qa@example.invalid>",
    )
    @patch("apps.participants.tasks.email_delivery_ready", return_value=True)
    def test_withdrawal_email_branding_and_privacy(self, _ready):
        from .tasks import send_enrollment_email
        challenge, token = self.issue("withdraw")
        self.assertEqual(send_enrollment_email.run(str(challenge.pk)), "sent")
        self.assertEqual(len(mail.outbox), 1)
        message=mail.outbox[0]
        self.assertIn("Confirmar retirada", message.body)
        self.assertIn(token, message.body)
        self.assertIn("A alteração só será concluída após confirmação", message.body)
        self.assertEqual(len(message.alternatives), 1)

    def test_enrollment_email_confirmation_is_once_only(self):
        challenge, token = self.issue(EnrollmentEmailChallenge.Purpose.VERIFY)
        self.assertIsNone(self.submission.email_verified_at)
        self.assertEqual(consume_challenge(token, "withdraw"), None)
        self.assertEqual(consume_challenge(token, "verify"), "email_verified")
        self.assertEqual(consume_challenge(token, "verify"), None)
        self.submission.refresh_from_db()
        challenge.refresh_from_db()
        self.assertEqual(self.submission.status, EnrollmentSubmission.Status.EMAIL_VERIFIED)
        self.assertIsNotNone(self.submission.email_verified_at)
        self.assertIsNotNone(challenge.consumed_at)
        self.assertEqual(ProgramParticipant.objects.count(), 0)

    def test_withdrawal_prevents_later_confirmation_and_disables_marketing(self):
        _, verification_token = self.issue("verify")
        _, removal_token = self.issue("withdraw")
        self.assertEqual(consume_challenge(removal_token, "withdraw"), "withdrawn")
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.marketing_opt_in)
        self.assertIsNotNone(self.submission.withdrawn_at)
        self.assertEqual(self.submission.status, EnrollmentSubmission.Status.WITHDRAWN)
        self.assertEqual(consume_challenge(verification_token, "verify"), None)
        self.assertEqual(consume_challenge(removal_token, "withdraw"), None)
        self.assertEqual(ProgramParticipant.objects.count(), 0)

    def test_expired_and_forged_tokens_are_rejected(self):
        challenge, token = self.issue("verify")
        EnrollmentEmailChallenge.objects.filter(pk=challenge.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertIsNone(consume_challenge(token, "verify"))
        self.assertIsNone(consume_challenge("Z" * 43, "verify"))
        self.assertIsNone(self.submission.email_verified_at)

    def test_public_email_action_requires_post_and_csrf(self):
        _, token = self.issue("verify")
        public = APIClient(enforce_csrf_checks=True)
        endpoint = reverse("public-enrollment-email-action")
        self.assertEqual(public.get(endpoint).status_code, 405)
        self.assertEqual(public.post(endpoint, {"token": token,"action":"verify"},
                                     format="json").status_code, 403)
        public.get(reverse("auth-session"))
        cookie = public.cookies.get("csrftoken")
        self.assertIsNotNone(cookie)
        confirm = public.post(
            endpoint, {"token":token,"action":"verify"},
            format="json",HTTP_X_CSRFTOKEN=cookie.value
        )
        self.assertEqual(confirm.status_code, 200, confirm.data)
        self.assertFalse(confirm.data["participant_created"])
        self.assertFalse(confirm.data["cashback_enabled"])
        replay = public.post(
            endpoint, {"token":token,"action":"verify"},
            format="json", HTTP_X_CSRFTOKEN=cookie.value,
        )
        self.assertEqual(replay.status_code, 410)

    def test_withdrawal_request_never_reveals_existing_email(self):
        url = reverse("public-store-withdraw-request", kwargs={"slug":self.tenant.slug})
        with patch("apps.participants.tasks.send_enrollment_email.delay") as delayed:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.client.post(url, {"email":"teste@example.invalid"}, format="json")
            self.assertEqual(first.status_code, 202, first.data)
            self.assertEqual(delayed.call_count, 1)
            nonexist = self.client.post(
                url, {"email":"nobody@example.invalid"}, format="json"
            )
            self.assertEqual(nonexist.status_code, 202)
            self.assertEqual(first.data, nonexist.data)
            repeated = self.client.post(url, {"email":"teste@example.invalid"}, format="json")
            self.assertEqual(repeated.data, first.data)
            self.assertEqual(delayed.call_count, 1)
        self.assertEqual(
            EnrollmentEmailChallenge.objects.filter(purpose="withdraw").count(), 1,
        )

    @override_settings(FIDELIZA_EMAIL_DELIVERY_ENABLED=False)
    def test_all_sending_disabled_by_default(self):
        with patch("apps.participants.tasks.send_enrollment_email.delay") as delayed:
            self.assertFalse(enqueue_confirmation(self.submission, "verify"))
            delayed.assert_not_called()
        self.assertEqual(EnrollmentEmailChallenge.objects.count(), 0)
        self.assertEqual(self.client.post(
            reverse("public-store-withdraw-request", kwargs={"slug":self.tenant.slug}),
            {"email":self.submission.email}, format="json",
        ).status_code, 503)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="mail.smtp2go.com", EMAIL_HOST_USER="gmail-vidalys",
        EMAIL_HOST_PASSWORD="test-only-not-secret",
        EMAIL_USE_TLS=True, EMAIL_USE_SSL=False,
        DEFAULT_FROM_EMAIL="Vidalys <contato@vidalys.com.br>",
    )
    def test_transactional_message_has_correct_sender_and_links(self):
        from .tasks import send_enrollment_email
        challenge, token = self.issue("verify")
        self.assertFalse(email_delivery_ready())  # locmem não pode ser habilitado em produção
        with patch("apps.participants.tasks.email_delivery_ready", return_value=True):
            result = send_enrollment_email.apply(
                args=(str(challenge.pk),), throw=True,
            ).get()
        self.assertEqual(result, "sent")
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.from_email, "Vidalys <contato@vidalys.com.br>")
        self.assertEqual(sent.to, ["teste@example.invalid"])
        self.assertIn("/confirmar#acao=verify&token=", sent.body)
        self.assertIn(token, sent.body)
        self.assertNotIn("test-only-not-secret", sent.body)
        self.assertIn("Loja de testes", sent.subject)
        self.assertEqual(ProgramParticipant.objects.count(), 0)
