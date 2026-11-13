"""Identidades dos lojistas, separadas dos cadastros de clientes dos programas."""
import uuid

from django.conf import settings
from django.db import models


class MerchantEmailIdentity(models.Model):
    """Um e-mail confirmado não pode pertencer a dois lojistas."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="merchant_email_identity")
    normalized_email = models.EmailField(max_length=254, unique=True)
    verified_at = models.DateTimeField()


class MerchantRegistration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    normalized_email = models.EmailField(max_length=254, unique=True)
    first_name = models.CharField(max_length=100)
    store_name = models.CharField(max_length=140)
    password_hash = models.CharField(max_length=256)
    requested_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    # Moderação feita pelo superusuário; não elimina contas já confirmadas.
    cancelled_at = models.DateTimeField(null=True, blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Cadastro de lojista"
        verbose_name_plural = "Cadastros de lojistas"


class MerchantPasswordReset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="merchant_password_resets")
    email_snapshot = models.EmailField(max_length=254)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MerchantEmailClaim(models.Model):
    """Um dono por caixa postal canônica (inclui aliases conhecidos do Gmail).

    Guarda atômica no PostgreSQL: duas confirmações concorrentes nunca
    conseguem criar dois lojistas para a mesma caixa postal.
    """
    canonical_email = models.EmailField(max_length=254, unique=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="merchant_email_claim")
    created_at = models.DateTimeField(auto_now_add=True)


class EmailDispatch(models.Model):
    """Auditoria sem PII do caminho API -> Redis -> worker -> SMTP."""
    class Kind(models.TextChoices):
        REGISTER = "register", "Confirmação de lojista"
        RESET = "reset", "Redefinição de senha"
        VERIFY = "verify", "Confirmação de participante"
        WITHDRAW = "withdraw", "Retirada de participante"
        MEMBER = "member", "Acesso ao clube do consumidor"

    class State(models.TextChoices):
        QUEUED = "queued", "Aguardando publicação"
        SENDING = "sending", "Enviando ao SMTP"
        RETRY = "retry", "Retentativa programada"
        ACCEPTED = "accepted", "Aceito pelo SMTP"
        PUBLISH_FAILED = "publish_failed", "Falha no Redis"
        FAILED = "failed", "Falha no SMTP"
        SKIPPED = "skipped", "Não enviado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    reference_id = models.UUIDField()
    state = models.CharField(max_length=20, choices=State.choices, default=State.QUEUED)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    failure_type = models.CharField(max_length=60, blank=True, default="")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Disparo de e-mail"
        verbose_name_plural = "Disparos de e-mail"
        indexes = [models.Index(fields=["state", "created_at"], name="core_mail_dispatch_idx")]
