"""Desafios para validar posse de e-mail e retirar solicitação sem liberar saldo.

Nunca armazena token em claro. Envio transacional em fila Celery privada.
Esta prova NÃO confirma identidade do cliente Nuvemshop.
"""
import base64
import hashlib
import hmac
import logging
import uuid
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission, EnrollmentCustomerLink
from .models import ProgramParticipant

logger = logging.getLogger(__name__)
TOKEN_LIFETIME = timedelta(minutes=30)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def make_token(challenge_id, purpose: str) -> str:
    """HMAC de UUID único; o token não precisa trafegar no broker Redis."""
    message = f"fideliza:email-proof:v1:{challenge_id}:{purpose}".encode("ascii")
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")


def email_links_enabled() -> bool:
    """API só precisa do domínio canônico, não da senha SMTP do worker."""
    if not settings.FIDELIZA_EMAIL_DELIVERY_ENABLED:
        return False
    base = urlparse(settings.FIDELIZA_PUBLIC_BASE_URL)
    return (base.scheme == "https" and bool(base.hostname) and not base.username
            and not base.password and not base.query and not base.fragment
            and not base.path.strip("/"))


def email_delivery_ready() -> bool:
    """No worker exige SMTP completo e remetente autorizado no provedor."""
    if not email_links_enabled():
        return False
    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        return False  # nunca imprimir links no log pelo console backend.
    if not (settings.EMAIL_HOST and settings.EMAIL_HOST_USER and
            settings.EMAIL_HOST_PASSWORD and settings.DEFAULT_FROM_EMAIL):
        return False
    if not (settings.EMAIL_USE_TLS or settings.EMAIL_USE_SSL):
        return False
    base = urlparse(settings.FIDELIZA_PUBLIC_BASE_URL)
    return (base.scheme == "https" and bool(base.hostname) and not base.username
            and not base.password and not base.query and not base.fragment
            and not base.path.strip("/") and not
            (settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL))


def enqueue_confirmation(submission: EnrollmentSubmission, purpose: str):
    """Emitir somente para conta não retirada, após commit, sem token no log."""
    if not email_links_enabled():
        return False
    if purpose not in (EnrollmentEmailChallenge.Purpose.VERIFY,
                       EnrollmentEmailChallenge.Purpose.WITHDRAW):
        return False
    if submission.status == EnrollmentSubmission.Status.WITHDRAWN:
        return False
    if submission.tenant.status != "active":
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
    challenge_id = uuid.uuid4()
    token = make_token(challenge_id, purpose)
    challenge = EnrollmentEmailChallenge.objects.create(
        id=challenge_id, submission=submission, purpose=purpose,
        token_digest=digest(token),
        expires_at=now + TOKEN_LIFETIME,
    )
    # Falha de fila não transforma registro em confirmação nem expõe token.
    def queue_mail():
        try:
            from .tasks import send_enrollment_email
            send_enrollment_email.delay(str(challenge.id))
        except Exception:
            logger.warning("Falha ao enfileirar confirmação (desafio %s)", challenge.id)

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
    submission = EnrollmentSubmission.objects.select_for_update().select_related(
        "tenant"
    ).get(pk=challenge.submission_id)
    if submission.tenant.status != "active":
        return None
    if submission.status == EnrollmentSubmission.Status.WITHDRAWN:
        return None
    if purpose == EnrollmentEmailChallenge.Purpose.VERIFY:
        if submission.email_verified_at is None:
            submission.email_verified_at = now
            submission.status = EnrollmentSubmission.Status.EMAIL_VERIFIED
            submission.save(update_fields=["email_verified_at", "status"])
    else:
        # Retirada imediata: impede futura promoção e marketing.
        # Se já foi participante, encerrar a adesão no mesmo commit.
        # O extrato é preservado para auditoria; nenhum resgate é executado.
        link = EnrollmentCustomerLink.objects.filter(submission=submission).first()
        if link:
            ProgramParticipant.objects.select_for_update().filter(
                pk=link.participant_id, tenant_id=submission.tenant_id,
            ).update(status=ProgramParticipant.Status.WITHDRAWN)
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
