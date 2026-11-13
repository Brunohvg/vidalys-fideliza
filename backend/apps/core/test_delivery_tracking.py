"""Publicação e envio observáveis sem PII, retry transitório e idempotência."""
from datetime import timedelta
from unittest.mock import patch, Mock
import smtplib

from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from .delivery_tracking import (
    enqueue_email, claim_delivery, finish_delivery, retry_or_fail,
)
from .models import EmailDispatch, MerchantRegistration
from .tasks import send_merchant_auth_email


class DispatchTrackingTests(TestCase):
    def setUp(self):
        self.register=MerchantRegistration.objects.create(
            normalized_email="qa@example.invalid",
            first_name="Teste", store_name="Loja",
            password_hash="hashed",
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    def test_publish_only_on_commit_and_record_queue_failure(self):
        task=Mock()
        task.delay.side_effect=ConnectionError("redis-private-host-should-not-leak")
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            enqueue_email("register",self.register.pk,task,"register",str(self.register.pk))
        self.assertEqual(len(callbacks),1)
        self.assertEqual(task.delay.call_count,1)
        row=EmailDispatch.objects.get()
        self.assertEqual(row.state,EmailDispatch.State.PUBLISH_FAILED)
        self.assertEqual(row.failure_type,"ConnectionError")
        self.assertIsNone(row.published_at)
        self.assertNotIn("redis-private-host-should-not-leak",repr(row.__dict__))

    def test_claim_and_complete_only_once(self):
        row=EmailDispatch.objects.create(kind="register",reference_id=self.register.pk)
        self.assertTrue(claim_delivery(str(row.pk)))
        self.assertFalse(claim_delivery(str(row.pk)))
        finish_delivery(str(row.pk),EmailDispatch.State.ACCEPTED)
        row.refresh_from_db()
        self.assertEqual(row.attempts,1)
        self.assertEqual(row.state,EmailDispatch.State.ACCEPTED)
        self.assertIsNotNone(row.finished_at)
        self.assertFalse(claim_delivery(str(row.pk)))

    def test_stuck_sending_not_sent_again_without_manual_audit(self):
        row=EmailDispatch.objects.create(kind="register",reference_id=self.register.pk,
                                         state=EmailDispatch.State.SENDING,
                                         started_at=timezone.now()-timedelta(hours=1))
        self.assertFalse(claim_delivery(str(row.pk)))
        self.assertEqual(EmailDispatch.objects.get(pk=row.pk).state,"sending")

    def test_retry_only_when_error_transient(self):
        row=EmailDispatch.objects.create(kind="register",reference_id=self.register.pk)
        self.assertTrue(claim_delivery(str(row.pk)))
        fake=Mock()
        fake.request.retries=0
        fake.max_retries=2
        fake.retry.side_effect=Retry()
        with self.assertRaises(Retry):
            retry_or_fail(fake,str(row.pk),smtplib.SMTPServerDisconnected("synthetic"))
        row.refresh_from_db()
        self.assertEqual(row.state,EmailDispatch.State.RETRY)
        self.assertEqual(fake.retry.call_args.kwargs["countdown"],10)
        self.assertTrue(claim_delivery(str(row.pk)))
        fake.request.retries=1
        with self.assertRaises(Retry):
            retry_or_fail(fake,str(row.pk),smtplib.SMTPResponseException(451,b"retry later"))
        self.assertEqual(fake.retry.call_args.kwargs["countdown"],20)
        self.assertTrue(claim_delivery(str(row.pk)))
        fake.request.retries=2
        with self.assertRaises(RuntimeError):
            retry_or_fail(fake,str(row.pk),smtplib.SMTPResponseException(554,b"rejected"))
        row.refresh_from_db()
        self.assertEqual(row.state,EmailDispatch.State.FAILED)
        self.assertEqual(row.attempts,3)

    @override_settings(
        FIDELIZA_PUBLIC_BASE_URL="https://fideliza-homolog.optarys.com.br",
        FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="Vidalys <qa@example.invalid>",
    )
    @patch("apps.core.tasks._smtp_ready", return_value=True)
    def test_merchant_worker_accepts_only_once(self, ready):
        row=EmailDispatch.objects.create(kind="register",reference_id=self.register.pk)
        self.assertEqual(send_merchant_auth_email.run("register",str(self.register.pk),str(row.pk)),"sent")
        self.assertEqual(send_merchant_auth_email.run("register",str(self.register.pk),str(row.pk)),"duplicate")
        row.refresh_from_db()
        self.assertEqual(row.state,EmailDispatch.State.ACCEPTED)
        self.assertEqual(row.attempts,1)
        self.assertEqual(len(mail.outbox),1)
        self.assertNotIn(self.register.normalized_email,row.failure_type)

    @override_settings(
        FIDELIZA_PUBLIC_BASE_URL="https://fideliza-homolog.optarys.com.br",
        FIDELIZA_EMAIL_DELIVERY_ENABLED=True,
    )
    @patch("apps.core.tasks._smtp_ready", return_value=True)
    @patch("apps.core.tasks.transactional_message", side_effect=ValueError("render failed confidential"))
    def test_render_failure_marks_dispatch_failed_without_leaking_details(self, _template, _ready):
        event = EmailDispatch.objects.create(
            kind=EmailDispatch.Kind.REGISTER, reference_id=self.register.pk
        )
        with self.assertRaises(RuntimeError):
            send_merchant_auth_email.run("register", str(self.register.pk), str(event.pk))
        event.refresh_from_db()
        self.assertEqual(event.state, EmailDispatch.State.FAILED)
        self.assertEqual(event.failure_type, "ValueError")
        self.assertEqual(event.attempts, 1)
        self.assertIsNotNone(event.finished_at)
        self.assertNotIn("confidential", str(event.__dict__))

    @override_settings(FIDELIZA_EMAIL_DELIVERY_ENABLED=False)
    def test_disabled_worker_has_visible_skipped_state(self):
        row=EmailDispatch.objects.create(kind="register",reference_id=self.register.pk)
        self.assertEqual(send_merchant_auth_email.run("register",str(self.register.pk),str(row.pk)),
                         "disabled")
        row.refresh_from_db()
        self.assertEqual(row.state,EmailDispatch.State.SKIPPED)
        self.assertEqual(row.failure_type,"disabled")

    def test_admin_readonly_superuser_only(self):
        from django.urls import reverse
        from django.test import override_settings
        row=EmailDispatch.objects.create(kind="register",reference_id=self.register.pk)
        url=reverse("admin:core_emaildispatch_changelist")
        self.assertEqual(self.client.get(url).status_code,302)
        customer=get_user_model().objects.create_user(username="merchant-qa",password="test-pass")
        self.client.force_login(customer)
        self.assertEqual(self.client.get(url).status_code,302)
        superuser=get_user_model().objects.create_superuser(
            username="super-qa",email="admin@example.invalid",password="StrongPass!2026")
        self.client.force_login(superuser)
        with override_settings(
            STORAGES={"staticfiles":{"BACKEND":"django.contrib.staticfiles.storage.StaticFilesStorage"}}
        ):
            page=self.client.get(url)
        self.assertEqual(page.status_code,200)
        self.assertContains(page,"Disparos de e-mail")
        self.assertNotContains(page,self.register.normalized_email)
        self.assertEqual(self.client.post(
            reverse("admin:core_emaildispatch_change",args=[row.pk]),{}).status_code,403)
