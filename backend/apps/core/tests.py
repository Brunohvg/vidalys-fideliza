from django.test import TestCase
from django.urls import reverse

class HealthTests(TestCase):
    def test_liveness(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness(self):
        response = self.client.get(reverse("ready"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")

    def test_requires_get(self):
        self.assertEqual(self.client.post(reverse("health")).status_code, 405)


class EmailDispatchLifecycleTests(TestCase):
    """G3: fila e auditoria não dependem de SMTP real nem geram e-mails."""
    def test_enqueue_is_published_only_after_commit(self):
        from unittest.mock import Mock
        from uuid import uuid4
        from .delivery_tracking import enqueue_email
        from .models import EmailDispatch

        task = Mock()
        ref = uuid4()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            event = enqueue_email(EmailDispatch.Kind.REGISTER, ref, task, "register", str(ref))
            self.assertFalse(task.delay.called)
        self.assertEqual(len(callbacks), 1)
        task.delay.assert_called_once_with("register", str(ref), str(event.pk))
        event.refresh_from_db()
        self.assertEqual(event.state, EmailDispatch.State.QUEUED)
        self.assertIsNotNone(event.published_at)

    def test_publish_failure_is_recorded_without_leaking_exception_message(self):
        from unittest.mock import Mock
        from uuid import uuid4
        from .delivery_tracking import enqueue_email
        from .models import EmailDispatch

        task = Mock()
        task.delay.side_effect = ConnectionError("sensitive endpoint text")
        with self.captureOnCommitCallbacks(execute=True):
            event = enqueue_email(EmailDispatch.Kind.RESET, uuid4(), task, "reset", "ref")
        event.refresh_from_db()
        self.assertEqual(event.state, EmailDispatch.State.PUBLISH_FAILED)
        self.assertEqual(event.failure_type, "ConnectionError")
        self.assertIsNone(event.published_at)
        self.assertIsNotNone(event.finished_at)

    def test_retry_claim_clears_finished_at_and_rejects_duplicates(self):
        from uuid import uuid4
        from .delivery_tracking import claim_delivery, finish_delivery
        from .models import EmailDispatch

        event = EmailDispatch.objects.create(
            kind=EmailDispatch.Kind.REGISTER, reference_id=uuid4(),
        )
        self.assertTrue(claim_delivery(event.pk))
        self.assertFalse(claim_delivery(event.pk))
        finish_delivery(event.pk, EmailDispatch.State.RETRY, "TimeoutError")
        event.refresh_from_db()
        self.assertIsNotNone(event.finished_at)
        self.assertEqual(event.attempts, 1)
        self.assertTrue(claim_delivery(event.pk))
        event.refresh_from_db()
        self.assertEqual(event.state, EmailDispatch.State.SENDING)
        self.assertEqual(event.attempts, 2)
        self.assertIsNone(event.finished_at)
        self.assertEqual(event.failure_type, "")
        finish_delivery(event.pk, EmailDispatch.State.ACCEPTED)
        self.assertFalse(claim_delivery(event.pk))
        event.refresh_from_db()
        self.assertEqual(event.state, EmailDispatch.State.ACCEPTED)
        self.assertIsNotNone(event.finished_at)
