"""Envio de confirmação e recuperação apenas pelo worker SMTP isolado."""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from .email_templates import transactional_message

from .merchant_auth import create_token, email_feature_ready, valid_token
from .models import MerchantRegistration, MerchantPasswordReset

logger = logging.getLogger(__name__)


def _smtp_ready():
    return bool(email_feature_ready() and
        settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and
        settings.EMAIL_HOST and settings.EMAIL_HOST_USER and
        settings.EMAIL_HOST_PASSWORD and settings.DEFAULT_FROM_EMAIL and
        (settings.EMAIL_USE_TLS != settings.EMAIL_USE_SSL))


@shared_task(bind=True, max_retries=2, default_retry_delay=60, ignore_result=True)
def send_merchant_auth_email(self, purpose, record_id):
    if purpose not in ("register", "reset") or not _smtp_ready():
        return "disabled"
    model = MerchantRegistration if purpose == "register" else MerchantPasswordReset
    try:
        record = model.objects.get(pk=record_id)
    except (model.DoesNotExist, ValueError):
        return "missing"
    token = create_token(purpose, record)
    if not valid_token(purpose, record, token):
        return "expired"
    recipient = (record.normalized_email if purpose == "register"
                 else record.email_snapshot)
    if purpose == "register":
        subject = "Confirme seu e-mail e comece no Vidalys Fideliza"
        title = "Sua loja está quase pronta."
        greeting = "Olá, " + record.first_name + "!"
        description = (
            "Você iniciou o cadastro da loja " + record.store_name +
            " no Vidalys Fideliza. Confirme seu e-mail para criar sua conta "
            "e acessar o painel. A conexão com a Nuvemshop é opcional."
        )
        action_label = "Confirmar meu e-mail"
        context = "Seu primeiro acesso"
        footer = "Esta mensagem confirma somente sua identidade de lojista. Nenhum benefício ou compra será ativado."
    else:
        subject = "Redefina sua senha com segurança | Vidalys Fideliza"
        title = "Vamos recuperar seu acesso."
        greeting = "Olá!"
        description = (
            "Recebemos uma solicitação para criar uma nova senha de acesso ao Vidalys Fideliza. "
            "Para continuar, use o botão abaixo. Sua senha atual permanecerá válida até a confirmação."
        )
        action_label = "Criar nova senha"
        context = "Segurança da sua conta"
        footer = "Se você não solicitou a redefinição, ignore esta mensagem; nenhuma alteração será feita."
    route = "confirmar-conta" if purpose == "register" else "redefinir-senha"
    link = settings.FIDELIZA_PUBLIC_BASE_URL.rstrip("/") + "/" + route + "#token=" + token
    safety = "Este link é pessoal, pode ser utilizado uma única vez e expira em 30 minutos. Nunca compartilhe seu link ou senha."
    plain, html = transactional_message(
        title=title, greeting=greeting, description=description,
        action_label=action_label, action_url=link, context=context,
        safety_note=safety, footer_note=footer,
    )
    try:
        message = EmailMultiAlternatives(subject, plain, settings.DEFAULT_FROM_EMAIL,
                                         [recipient])
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        return "sent"
    except Exception as exc:
        # Não imprimir token, endereço, URL nem credenciais.
        logger.warning("Falha SMTP de autenticação: %s", type(exc).__name__)
        raise self.retry(exc=exc) from None
