"""Envio SMTP transacional no worker; mesmo contrato EMAIL_* do Mérito.

O broker Redis interno transporta tokens efêmeros. Não publicar token,
recipient, credencial ou link em logs.
"""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from apps.core.email_templates import transactional_message
from django.utils import timezone
from celery import shared_task
from .email_proof import digest, email_delivery_ready, make_token
from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60,
             acks_late=True, ignore_result=True)
def send_enrollment_email(self, challenge_id: str):
    if not email_delivery_ready():
        return "delivery_disabled"
    try:
        challenge = EnrollmentEmailChallenge.objects.select_related(
            "submission__tenant",
        ).get(pk=challenge_id)
    except EnrollmentEmailChallenge.DoesNotExist:
        return "not_found"
    token = make_token(challenge.id, challenge.purpose)
    if (challenge.token_digest != digest(token)
            or challenge.consumed_at is not None
            or challenge.expires_at <= timezone.now()
            or challenge.submission.status == EnrollmentSubmission.Status.WITHDRAWN
            or challenge.submission.tenant.status != Tenant.Status.ACTIVE):
        return "expired"
    submission = challenge.submission
    purpose = challenge.purpose
    if purpose == EnrollmentEmailChallenge.Purpose.VERIFY:
        subject = "Confirme seu e-mail | Clube " + submission.tenant.name
        title = "Sua participação começa por aqui."
        description = (
            "Você solicitou participar do programa de fidelidade de " +
            submission.tenant.name + ". Para continuar com segurança, "
            "precisamos confirmar que este endereço de e-mail pertence a você."
        )
        action_label = "Confirmar meu e-mail"
        context = "Confirmação de participação"
        footer = ("Este e-mail é enviado pelo Vidalys Fideliza a pedido de " +
                  submission.tenant.name +
                  ". Confirmar o endereço não ativa cashback, pontos ou compras automaticamente.")
    else:
        subject = "Confirme sua solicitação de retirada | " + submission.tenant.name
        title = "Você tem o controle."
        description = (
            "Recebemos um pedido de retirada da sua solicitação no programa de " +
            submission.tenant.name +
            ". Se deseja prosseguir, confirme pelo botão abaixo."
        )
        action_label = "Confirmar retirada"
        context = "Privacidade e preferências"
        footer = ("Se não pediu a retirada, ignore esta mensagem. "
                  "A alteração só será concluída após confirmação.")
    url = (settings.FIDELIZA_PUBLIC_BASE_URL.rstrip("/") +
           "/confirmar#acao=" + purpose + "&token=" + token)
    plain, html = transactional_message(
        title=title, greeting="Olá, " + submission.name + "!",
        description=description, action_label=action_label,
        action_url=url, context=context,
        safety_note="Este link é individual, válido por 30 minutos e pode ser utilizado uma única vez. Não encaminhe para outras pessoas.",
        footer_note=footer,
    )
    try:
        message = EmailMultiAlternatives(
            subject=subject, body=plain, from_email=settings.DEFAULT_FROM_EMAIL,
            to=[submission.email],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        return "sent"
    except Exception as exc:
        logger.warning("Envio transacional falhou (tipo=%s, tentativa=%d)",
                       type(exc).__name__, self.request.retries + 1)
        raise self.retry(exc=exc) from None
