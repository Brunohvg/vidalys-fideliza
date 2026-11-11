"""Envio SMTP transacional no worker; mesmo contrato EMAIL_* do Mérito.

O broker Redis interno transporta tokens efêmeros. Não publicar token,
recipient, credencial ou link em logs.
"""
import logging
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone
from celery import shared_task
from .email_proof import digest, email_delivery_ready
from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60,
             acks_late=True, ignore_result=True)
def send_enrollment_email(self, challenge_id: str, token: str):
    if not email_delivery_ready():
        return "delivery_disabled"
    try:
        challenge = EnrollmentEmailChallenge.objects.select_related(
            "submission__tenant",
        ).get(pk=challenge_id)
    except EnrollmentEmailChallenge.DoesNotExist:
        return "not_found"
    if (challenge.token_digest != digest(token)
            or challenge.consumed_at is not None
            or challenge.expires_at <= timezone.now()
            or challenge.submission.status == EnrollmentSubmission.Status.WITHDRAWN):
        return "expired"
    submission = challenge.submission
    purpose = challenge.purpose
    if purpose == EnrollmentEmailChallenge.Purpose.VERIFY:
        subject = f"Confirme seu e-mail | {submission.tenant.name}"
        intro = (
            f"Você solicitou participar do programa de fidelidade de {submission.tenant.name}.\n"
            "Confirme que este e-mail pertence a você para continuar a análise da solicitação.\n"
        )
        label = "Confirmar meu e-mail"
    else:
        subject = f"Retirar minha solicitação | {submission.tenant.name}"
        intro = (
            f"Foi solicitada a retirada da adesão ao programa de {submission.tenant.name}.\n"
            "Use o link para encerrar a solicitação. Nenhuma retirada ocorre sem confirmação.\n"
        )
        label = "Retirar minha solicitação"
    url = (settings.FIDELIZA_PUBLIC_BASE_URL.rstrip("/") +
           "/confirmar#acao=" + purpose + "&token=" + token)
    content = (
        "VIDALYS FIDELIZA — Confirmação de segurança\n\n"
        + intro + "\n" + label + ":\n" + url
        + "\n\nEste link expira em 30 minutos e pode ser usado apenas uma vez."
        + "\nSe não solicitou isso, ignore esta mensagem."
        + "\n\nA confirmação de e-mail não ativa cashback nem confirma compras na Nuvemshop."
        + "\nTecnologia Vidalys."
    )
    try:
        EmailMessage(
            subject=subject,
            body=content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[submission.email],
        ).send(fail_silently=False)
        return "sent"
    except Exception as exc:
        logger.warning("Envio transacional falhou (tipo=%s, tentativa=%d)",
                       type(exc).__name__, self.request.retries + 1)
        raise self.retry(exc=exc) from None
