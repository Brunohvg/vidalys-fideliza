"""Caixa de entrada de eventos de pedido, sem dados pessoais ou efeito financeiro.

Cada notificação indica somente que o pedido deve ser conferido novamente
pela API oficial. A chegada do webhook nunca comprova liquidação.
"""
import uuid
from django.db import models


class OrderWebhookEvent(models.Model):
    class Topic(models.TextChoices):
        PAID = "order/paid", "Pagamento reportado"
        UPDATED = "order/updated", "Pedido alterado"
        # Não é webhook: entrada de reconciliação criada pelo crédito desde a adesão quando a
        # busca na Nuvemshop acha um pedido dela cujo aviso nunca chegou. Passa pela mesma
        # reconsulta; o tópico deixa a origem auditável e não aciona o vínculo de cupom antigo.
        BACKFILL = "reconcile/backfill", "Reconciliação (sem webhook)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE,
        related_name="order_webhook_events",
    )
    store_id = models.CharField(max_length=64)
    order_id = models.CharField(max_length=64)
    topic = models.CharField(max_length=24, choices=Topic.choices)
    # Nem todo evento enviado pelo provedor contém este campo.
    event_launch_ts = models.BigIntegerField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=64, unique=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(
                fields=["tenant", "received_at"],
                name="nuv_order_evt_tenant_idx",
            ),
        ]
