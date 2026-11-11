"""Protocolo mínimo de solicitações LGPD Nuvemshop.

Jamais armazenar body de webhook, e-mail, telefone, documento ou token.
A recepção não equivale a conclusão da eliminação ou envio de dados.
"""
import uuid
from django.db import models


class PrivacyWebhookRequest(models.Model):
    class Topic(models.TextChoices):
        CUSTOMER_REDACT = "customer/redact", "Excluir dados do consumidor"
        CUSTOMER_DATA_REQUEST = "customers/data_request", "Relatório de dados do consumidor"
        STORE_REDACT = "app/store_redact", "Excluir dados da loja"

    class State(models.TextChoices):
        PENDING = "pending", "Aguardando tratamento"
        NEEDS_REVIEW = "needs_review", "Exige revisão de privacidade"
        COMPLETED = "completed", "Concluído após verificação"
        UNKNOWN_STORE = "unknown_store", "Loja não associada ao aplicativo"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.SET_NULL,
                               null=True, blank=True, related_name="privacy_requests")
    store_id = models.CharField(max_length=64)
    customer_id = models.CharField(max_length=64, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")
    topic = models.CharField(max_length=40, choices=Topic.choices)
    event_key = models.CharField(max_length=64, unique=True)
    state = models.CharField(max_length=20, choices=State.choices,
                             default=State.PENDING)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    # Apenas código controlado, nunca body com PII ou mensagem de exceção.
    reason_code = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["tenant", "state", "received_at"],
                         name="nuv_priv_tenant_state_idx"),
        ]
