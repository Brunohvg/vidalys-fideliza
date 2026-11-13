"""Medição de envio sem gravar tokens, destinatários ou mensagens.

'accepted' significa aceitação pelo SMTP, não entrega ao destinatário.
Atrasos, rejeições e entregas exigem confirmação no provedor de e-mail.
"""
import logging
import smtplib

from celery.exceptions import Retry
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import EmailDispatch

logger = logging.getLogger(__name__)


def enqueue_email(kind, reference_id, task, *args):
    """Registra evento no DB e publica somente após commit do cadastro."""
    event = EmailDispatch.objects.create(kind=kind, reference_id=reference_id)

    def publish():
        # Timestamp anterior ao envio: o worker pode iniciar antes do ACK do Redis.
        # Somente persistir se a publicação terminar sem erro.
        publication_started = timezone.now()
        try:
            task.delay(*args, str(event.pk))
        except Exception as exc:
            EmailDispatch.objects.filter(
                pk=event.pk, state=EmailDispatch.State.QUEUED
            ).update(
                state=EmailDispatch.State.PUBLISH_FAILED,
                failure_type=type(exc).__name__[:60],
                finished_at=timezone.now(),
            )
            logger.error("email_dispatch queue_failed kind=%s event=%s type=%s",
                         kind, event.pk, type(exc).__name__)
        else:
            # O worker pode executar antes de a API atualizar published_at.
            EmailDispatch.objects.filter(pk=event.pk).update(published_at=publication_started)
            logger.info("email_dispatch queued kind=%s event=%s", kind, event.pk)

    transaction.on_commit(publish)
    return event


def claim_delivery(event_id):
    """Claim atômico de no máximo uma execução simultânea para cada disparo."""
    if event_id is None:  # Fila antiga durante atualização: payload não inclui auditoria.
        return True
    return bool(EmailDispatch.objects.filter(
        pk=event_id, state__in=(EmailDispatch.State.QUEUED, EmailDispatch.State.RETRY)
    ).update(
        state=EmailDispatch.State.SENDING,
        started_at=timezone.now(),
        attempts=F("attempts") + 1,
        failure_type="",
        finished_at=None,
    ))


def finish_delivery(event_id, state, failure=""):
    if event_id is None:
        return
    EmailDispatch.objects.filter(pk=event_id, state=EmailDispatch.State.SENDING).update(
        state=state,
        failure_type=failure[:60],
        finished_at=timezone.now(),
    )
    row = EmailDispatch.objects.filter(pk=event_id).values(
        "kind", "created_at", "published_at", "started_at", "finished_at", "attempts",
    ).first()
    if row:
        queued_at = row["published_at"]
        started_at = row["started_at"]
        finished_at = row["finished_at"]
        queue_s = round((started_at-queued_at).total_seconds(), 1) if started_at and queued_at else None
        smtp_s = round((finished_at-started_at).total_seconds(), 1) if finished_at and started_at else None
        logger.info(
            "email_dispatch state=%s kind=%s event=%s queue_s=%s smtp_s=%s attempts=%s",
            state, row["kind"], event_id, queue_s, smtp_s, row["attempts"],
        )


def retry_or_fail(task, event_id, exc):
    """Retentativas somente em falhas SMTP transitórias, 10s e 20s."""
    error_type = type(exc).__name__
    code = getattr(exc, "smtp_code", None)
    temporary = (
        isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                         TimeoutError, ConnectionError, OSError))
        or isinstance(code, int) and 400 <= code < 500
    )
    if temporary and task.request.retries < task.max_retries:
        finish_delivery(event_id, EmailDispatch.State.RETRY, error_type)
        logger.warning("email_dispatch transient_smtp type=%s retry=%d",
                       error_type, task.request.retries + 1)
        try:
            raise task.retry(
                exc=RuntimeError("SMTP temporariamente indisponível"),
                countdown=10 * 2 ** task.request.retries,
            ) from None
        except Retry:
            # O Celery utiliza essa exceção para sinalizar retry bem agendado.
            raise
        except Exception as publish_exc:
            # Falha ao publicar o retry no Redis: não deixar tarefa fantasma
            # em "retry" e não reenviar automaticamente (SMTP pode ter aceito).
            if event_id is not None:
                EmailDispatch.objects.filter(
                    pk=event_id, state=EmailDispatch.State.RETRY,
                ).update(
                    state=EmailDispatch.State.PUBLISH_FAILED,
                    finished_at=timezone.now(),
                    failure_type=type(publish_exc).__name__[:60],
                )
            logger.error(
                "email_dispatch retry_publish_failed event=%s type=%s",
                event_id, type(publish_exc).__name__,
            )
            raise RuntimeError("Falha ao reagendar envio") from None
    finish_delivery(event_id, EmailDispatch.State.FAILED, error_type)
    logger.error("email_dispatch terminal_smtp type=%s", error_type)
    raise RuntimeError("Falha de envio SMTP") from None
