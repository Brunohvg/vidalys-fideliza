"""Envio SMTP transacional no worker; mesmo contrato EMAIL_* do Mérito.

O broker Redis interno transporta tokens efêmeros. Não publicar token,
recipient, credencial ou link em logs.
"""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from apps.core.email_templates import transactional_message
from apps.core.delivery_tracking import claim_delivery, finish_delivery, retry_or_fail
from apps.core.models import EmailDispatch
from django.utils import timezone
from celery import shared_task
from .email_proof import digest, email_delivery_ready, make_token
from .enrollment_models import EnrollmentEmailChallenge, EnrollmentSubmission
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60,
             acks_late=True, ignore_result=True)
def send_enrollment_email(self, challenge_id: str, event_id=None):
    if not claim_delivery(event_id):
        return "duplicate"
    if not email_delivery_ready():
        finish_delivery(event_id, EmailDispatch.State.SKIPPED, "disabled")
        return "delivery_disabled"
    try:
        challenge = EnrollmentEmailChallenge.objects.select_related(
            "submission__tenant",
        ).get(pk=challenge_id)
    except EnrollmentEmailChallenge.DoesNotExist:
        finish_delivery(event_id, EmailDispatch.State.SKIPPED, "missing")
        return "not_found"
    try:
        token = make_token(challenge.id, challenge.purpose)
        if (challenge.token_digest != digest(token)
                or challenge.consumed_at is not None
                or challenge.expires_at <= timezone.now()
                or challenge.submission.status == EnrollmentSubmission.Status.WITHDRAWN
                or challenge.submission.tenant.status != Tenant.Status.ACTIVE):
            finish_delivery(event_id, EmailDispatch.State.SKIPPED, "expired")
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
        message = EmailMultiAlternatives(
            subject=subject, body=plain, from_email=settings.DEFAULT_FROM_EMAIL,
            to=[submission.email],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        finish_delivery(event_id, EmailDispatch.State.ACCEPTED)
        return "sent"
    except Exception as exc:
        retry_or_fail(self, event_id, exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60,
             acks_late=True, ignore_result=True)
def send_member_access_email(self, challenge_id: str, event_id=None):
    """Token HMAC é derivado no worker; Redis recebe somente UUIDs."""
    from .enrollment_models import MemberAccessChallenge
    from .email_proof import make_token, digest
    if not claim_delivery(event_id):
        return "duplicate"
    if not email_delivery_ready():
        finish_delivery(event_id, EmailDispatch.State.SKIPPED, "disabled")
        return "delivery_disabled"
    try:
        challenge = MemberAccessChallenge.objects.select_related(
            "submission__tenant",
        ).get(pk=challenge_id)
    except MemberAccessChallenge.DoesNotExist:
        finish_delivery(event_id, EmailDispatch.State.SKIPPED, "missing")
        return "not_found"
    try:
        submission = challenge.submission
        token = make_token(challenge.id, "member")
        if (challenge.token_digest != digest(token)
                or challenge.consumed_at is not None
                or challenge.expires_at <= timezone.now()
                or submission.email_verified_at is None
                or submission.withdrawn_at is not None
                or submission.status not in (
                    EnrollmentSubmission.Status.EMAIL_VERIFIED,
                    EnrollmentSubmission.Status.LINKED,
                )
                or submission.tenant.status != Tenant.Status.ACTIVE):
            finish_delivery(event_id, EmailDispatch.State.SKIPPED, "expired")
            return "expired"
        url = (settings.FIDELIZA_PUBLIC_BASE_URL.rstrip("/")
               + "/clube/" + submission.tenant.slug + "#acesso=" + token)
        plain, html = transactional_message(
            title="Seu Clube de Vantagens",
            greeting="Olá, " + submission.name + "!",
            description=("Você pediu um acesso privado ao Clube " +
                         submission.tenant.name +
                         ". Use o botão abaixo para acompanhar sua participação e as regras."),
            action_label="Acessar Meu Clube",
            action_url=url,
            context="Acesso privado do participante",
            safety_note="Link pessoal, válido por 15 minutos e de uso único. Não encaminhe.",
            footer_note="Se você não pediu este acesso, ignore o e-mail. Nenhum ponto ou recompensa é criado por este link.",
        )
        message = EmailMultiAlternatives(
            subject="Acesse seu clube | " + submission.tenant.name,
            body=plain, from_email=settings.DEFAULT_FROM_EMAIL,
            to=[submission.email],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        finish_delivery(event_id, EmailDispatch.State.ACCEPTED)
        return "sent"
    except Exception as exc:
        retry_or_fail(self, event_id, exc)
