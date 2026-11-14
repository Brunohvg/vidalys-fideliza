"""Vendas de múltiplos canais: prova e regras antes de qualquer crédito.

Uma venda aqui é apenas fato operacional; NÃO cria pontos ou dinheiro.
O mesmo registro é referenciado por tenant, canal e documento da origem.
"""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class SaleRecord(models.Model):
    class Channel(models.TextChoices):
        COUNTER = "counter", "Balcão"
        NUVEMSHOP = "nuvemshop", "Nuvemshop"
        WHATSAPP = "whatsapp", "WhatsApp"
        VIDALYS_FLOW = "vidalys_flow", "Vidalys Flow"

    class State(models.TextChoices):
        AWAITING_MEMBER = "awaiting_member", "Sem participante"
        AWAITING_REVIEW = "awaiting_review", "Conferência pendente"
        VERIFIED_MANUAL = "verified_manual", "Venda manual conferida"
        REJECTED = "rejected", "Rejeitada"

    class OrderStatus(models.TextChoices):
        PENDING = "pending", "Pendente (informado)"
        PAID = "paid", "Pago (informado; não conciliado)"
        CANCELLED = "cancelled", "Cancelado"
        REFUNDED = "refunded", "Estornado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="sales_records")
    participant = models.ForeignKey(
        "participants.ProgramParticipant", on_delete=models.PROTECT,
        null=True, blank=True, related_name="sales_records",
    )
    channel = models.CharField(max_length=16, choices=Channel.choices)
    external_reference = models.CharField(max_length=80)
    # Compras de canais externos começam com elegibilidade NÃO verificada (0).
    eligible_amount_cents = models.PositiveBigIntegerField()
    reported_total_cents = models.PositiveBigIntegerField(default=0)
    order_status = models.CharField(
        max_length=12, choices=OrderStatus.choices, default=OrderStatus.PENDING,
    )
    source_order_key = models.CharField(max_length=64, blank=True, default="")
    reported_contact_digest = models.CharField(max_length=64, blank=True, default="")
    customer_profile = models.ForeignKey(
        "customers.CustomerProfile", on_delete=models.PROTECT,
        null=True, blank=True, related_name="channel_sales",
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="BRL", editable=False)
    reported_paid_at = models.DateTimeField(null=True, blank=True)
    evidence_reference = models.CharField(max_length=80, blank=True, default="")
    state = models.CharField(max_length=24, choices=State.choices, default=State.AWAITING_REVIEW)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="submitted_manual_sales",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="reviewed_manual_sales",
    )
    review_note = models.CharField(max_length=240, blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "channel", "external_reference"],
                name="sales_unique_channel_document",
            ),
            models.CheckConstraint(
                condition=Q(eligible_amount_cents__gte=0),
                name="sales_nonnegative_eligible_amount",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "state", "created_at"], name="sales_tenant_state_idx"),
        ]


class SaleEventReceipt(models.Model):
    """Histórico append-only de recepção. Evento 'paid' NÃO comprova captura no PSP."""

    class Outcome(models.TextChoices):
        APPLIED = "applied", "Estado aplicado"
        IGNORED = "ignored", "Notificação antiga ou inválida para avançar estado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    sale = models.ForeignKey(SaleRecord, on_delete=models.PROTECT, related_name="inbound_events")
    channel = models.CharField(max_length=24)
    source_event_id = models.CharField(max_length=80, blank=True, default="")
    idempotency_key = models.CharField(max_length=64, unique=True)
    payload_digest = models.CharField(max_length=64)
    reported_status = models.CharField(max_length=12, choices=SaleRecord.OrderStatus.choices)
    reported_total_cents = models.PositiveBigIntegerField()
    outcome = models.CharField(max_length=12, choices=Outcome.choices)
    occurred_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "channel", "source_event_id"],
                condition=~Q(source_event_id=""),
                name="sales_source_event_once",
            ),
        ]
        indexes = [
            models.Index(fields=["sale", "received_at"], name="sales_inbox_sale_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Evento de venda é imutável.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Evento de venda não pode ser excluído.")


class PointRuleDraft(models.Model):
    """Simulação versionada da regra. Não concede pontos e não é uma regra ativa."""
    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="point_rule_draft",
    )
    version = models.PositiveIntegerField(default=1)
    points = models.PositiveIntegerField(default=1)
    per_cents = models.PositiveIntegerField(default=100)
    hold_days = models.PositiveSmallIntegerField(default=7)
    validity_days = models.PositiveSmallIntegerField(default=180)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="saved_point_rules",
    )
    updated_at = models.DateTimeField(auto_now=True)


class DiscountRewardDraft(models.Model):
    """Catálogo do clube: visibilidade pública não autoriza uso financeiro."""
    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PUBLISHED = "published", "Publicado para consulta"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="discount_reward_drafts")
    title = models.CharField(max_length=100)
    points_cost = models.PositiveIntegerField()
    discount_cents = models.PositiveIntegerField()
    min_order_cents = models.PositiveIntegerField(default=0)
    max_redemptions = models.PositiveIntegerField(default=100)
    publication_status = models.CharField(
        max_length=12, choices=PublicationStatus.choices, default=PublicationStatus.DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="discount_reward_drafts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(points_cost__gt=0), name="reward_draft_points_positive"),
            models.CheckConstraint(condition=Q(discount_cents__gt=0), name="reward_draft_discount_positive"),
        ]


class PointCampaignDraft(models.Model):
    """Ação de marketing em pontos, sem publicação nem disparo."""
    class Goal(models.TextChoices):
        SECOND = "second_purchase", "Segunda compra"
        REACTIVATION = "reactivation", "Recuperar clientes"
        RECURRENCE = "recurrence", "Estimular recorrência"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="point_campaign_drafts")
    goal = models.CharField(max_length=24, choices=Goal.choices)
    bonus_points = models.PositiveIntegerField()
    max_customers = models.PositiveIntegerField()
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="point_campaign_drafts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(bonus_points__gt=0), name="point_campaign_bonus_positive"),
            models.CheckConstraint(condition=Q(max_customers__gt=0), name="point_campaign_max_customers_positive"),
        ]
