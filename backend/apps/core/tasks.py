"""Envio de confirmação e recuperação apenas pelo worker SMTP isolado."""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage

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
    subject = ("Confirme seu cadastro | Vidalys Fideliza" if purpose == "register"
               else "Redefina sua senha | Vidalys Fideliza")
    route = "confirmar-conta" if purpose == "register" else "redefinir-senha"
    recipient = (record.normalized_email if purpose == "register"
                 else record.email_snapshot)
    link = settings.FIDELIZA_PUBLIC_BASE_URL.rstrip("/") + "/" + route + "#token=" + token
    text = (
        "VIDALYS FIDELIZA\n\n"
        + ("Confirme seu e-mail para concluir o cadastro do seu acesso de lojista."
           if purpose == "register" else
           "Você solicitou redefinir a senha da sua conta de lojista.")
        + "\n\nAbra o link:\n" + link
        + "\n\nO link expira em 30 minutos e só funciona uma vez."
        + "\nSe você não fez a solicitação, ignore esta mensagem."
    )
    try:
        EmailMessage(subject, text, settings.DEFAULT_FROM_EMAIL, [recipient]).send(
            fail_silently=False
        )
        return "sent"
    except Exception as exc:
        # Não imprimir token, endereço, URL nem credenciais.
        logger.warning("Falha SMTP de autenticação: %s", type(exc).__name__)
        raise self.retry(exc=exc) from None
