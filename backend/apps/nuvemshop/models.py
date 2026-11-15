"""Registros de autorização OAuth; tokens são armazenados apenas cifrados."""
import uuid
from django.conf import settings
from django.db import models


class OAuthAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    state_digest = models.CharField(max_length=64, unique=True)
    session_digest = models.CharField(max_length=64)
    client_id = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["expires_at"], name="nuv_oauth_exp_idx")]


class NuvemshopInstallation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE,
                                  related_name="nuvemshop_installation")
    client_id = models.CharField(max_length=64)
    store_id = models.CharField(max_length=64)
    token_ciphertext = models.TextField()
    scope = models.CharField(max_length=240)
    connected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                     on_delete=models.SET_NULL)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["client_id", "store_id"], name="nuv_unique_app_store"
        )]

# Registro de notificações obrigatórias LGPD.
from .privacy_models import PrivacyWebhookRequest  # noqa: E402,F401

# Recebimento mínimo dos avisos de pedido, sem efeito financeiro.
from .order_webhook_models import OrderWebhookEvent  # noqa: E402,F401


class NuvemshopCouponIntent(models.Model):
    """Um único cupom externo por voucher; sem código bearer em texto puro."""
    class State(models.TextChoices):
        PREPARED = "prepared", "Preparado"
        UNCERTAIN = "uncertain", "Resultado HTTP desconhecido"
        ISSUED = "issued", "Criado no provedor"
        APPLIED = "applied_pending_proof", "Aplicado, captura não comprovada"
        SETTLED = "settled", "Baixa financeira validada"
        REVOKING = "revoking", "Revogação em processamento"
        REVOKE_UNKNOWN = "revoke_unknown", "Exclusão remota pendente de confirmação"
        REVOKED = "revoked", "Cupom confirmado como revogado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    voucher = models.OneToOneField("loyalty.LoyaltyVoucher",
        on_delete=models.PROTECT, related_name="nuvemshop_coupon")
    store_id = models.CharField(max_length=64)
    encrypted_code = models.TextField()
    code_sha256 = models.CharField(max_length=64, unique=True)
    remote_coupon_id = models.CharField(max_length=64, blank=True, default="")
    order_id = models.CharField(max_length=32, blank=True, default="")
    state = models.CharField(max_length=24, choices=State.choices,
                             default=State.PREPARED)
    revoke_reason = models.CharField(max_length=24, blank=True, default="")
    revoked_at = models.DateTimeField(null=True, blank=True)
    # Persistir prova anterior da API de que o cupom nunca foi usado.
    verified_unused_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "order_id"],
                condition=~models.Q(order_id=""),
                name="nuv_pilot_one_coupon_per_order",
            ),
        ]


class NuvemshopOrderRecheck(models.Model):
    """Resultado mínimo da reconsulta OAuth, sem PII ou prova PSP inventada."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField("nuvemshop.OrderWebhookEvent",
        on_delete=models.PROTECT, related_name="order_recheck")
    status = models.CharField(max_length=24, default="pending")
    summary_digest = models.CharField(max_length=64, blank=True, default="")
    checked_at = models.DateTimeField(null=True, blank=True)
