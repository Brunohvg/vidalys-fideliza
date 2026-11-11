"""Desafios para validar posse de e-mail e retirar solicitação sem liberar saldo.

Nunca armazena token em claro. Envio transacional em fila Celery privada.
Esta prova NÃO confirma identidade do cliente Nuvemshop.
"""
import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission

logger = logging.getLogger(__name__)
TOKEN_LIFETIME = timedelta(minutes=30)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def email_delivery_ready() -> bool:
    """Exige remetente validado no provedor; a checagem DNS é externa."""
    if not settings.FIDELIZA_EMAIL_DELIVERY_ENABLED:
        return False
    if not (settings.EMAIL_HOST and settings.EMAIL_HOST_USER and
            settings.EMAIL_HOST_PASSWORD and settings.DEFAULT_FROM_EMAIL):
        return False
    base = urlparse(settings.FIDELIZA_PUBLIC_BASE_URL)
    return (base.scheme == "https" and bool(base.hostname) and not base.username
            and not base.password and not base.query and not base.fragment
            and not base.path.strip("/") and not
            (settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL))


def enqueue_confirmation(submission: EnrollmentSubmission, purpose: str):
    """Emitir somente para conta não retirada, após commit, sem token no log."""
    if not email_delivery_ready():
        return False
    if purpose not in (EnrollmentEmailChallenge.Purpose.VERIFY,
                       EnrollmentEmailChallenge.Purpose.WITHDRAW):
        return False
    if submission.status == EnrollmentSubmission.Status.WITHDRAWN:
        return False
    if purpose == EnrollmentEmailChallenge.Purpose.VERIFY and (
            submission.email_verified_at is not None):
        return False
    # Não acumular tokens válidos para o mesmo evento.
    now = timezone.now()
    if EnrollmentEmailChallenge.objects.filter(
        submission=submission, purpose=purpose, consumed_at__isnull=True,
        expires_at__gt=now,
    ).exists():
        return False
    token = secrets.token_urlsafe(32)
    challenge = EnrollmentEmailChallenge.objects.create(
        submission=submission, purpose=purpose, token_digest=digest(token),
        expires_at=now + TOKEN_LIFETIME,
    )
    # Falha de fila não transforma registro em confirmação nem expõe token.
    def queue_mail():
        try:
            from .tasks import send_enrollment_email
            send_enrollment_email.delay(str(challenge.id), token)
        except Exception:
            logger.exception("Não foi possível enfileirar confirmação (desafio %s)", challenge.id)

    transaction.on_commit(queue_mail)
    return True


@transaction.atomic
def consume_challenge(token: str, purpose: str):
    """Troca de estado única sob lock; token/objetivo devem corresponder."""
    if purpose not in (EnrollmentEmailChallenge.Purpose.VERIFY,
                       EnrollmentEmailChallenge.Purpose.WITHDRAW):
        return None
    now = timezone.now()
    challenge = EnrollmentEmailChallenge.objects.select_for_update().filter(
        token_digest=digest(token), purpose=purpose, consumed_at__isnull=True,
        expires_at__gt=now,
    ).first()
    if not challenge:
        return None
    submission = EnrollmentSubmission.objects.select_for_update().get(pk=challenge.submission_id)
    if submission.status == EnrollmentSubmission.Status.WITHDRAWN:
        return None
    if purpose == EnrollmentEmailChallenge.Purpose.VERIFY:
        if submission.email_verified_at is None:
            submission.email_verified_at = now
            submission.status = EnrollmentSubmission.Status.EMAIL_VERIFIED
            submission.save(update_fields=["email_verified_at", "status"])
    else:
        # Retirada imediata: impede futura promoção e marketing.
        submission.withdrawn_at = now
        submission.status = EnrollmentSubmission.Status.WITHDRAWN
        submission.marketing_opt_in = False
        submission.save(update_fields=["withdrawn_at", "status", "marketing_opt_in"])
        EnrollmentEmailChallenge.objects.filter(
            submission=submission, consumed_at__isnull=True,
        ).update(consumed_at=now)
    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at"])
    return submission.status
