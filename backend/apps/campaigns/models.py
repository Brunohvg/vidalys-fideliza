"""Planejamento persistido, separado de campanhas ativas e do motor de crédito."""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class CampaignDraft(models.Model):
    class Goal(models.TextChoices):
        SECOND_PURCHASE = "second_purchase", "Segunda compra"
        REACTIVATION = "reactivation", "Reativação"
        RECURRENCE = "recurrence", "Recorrência"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="campaign_drafts")
    title = models.CharField(max_length=90)
    goal = models.CharField(max_length=24, choices=Goal.choices)
    cashback_rate_bps = models.PositiveSmallIntegerField()
    ticket_cents = models.PositiveBigIntegerField()
    projected_paid_orders = models.PositiveIntegerField()
    budget_cents = models.PositiveBigIntegerField()
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(cashback_rate_bps__gte=1, cashback_rate_bps__lte=1000),
                name="draft_cashback_bps_range",
            ),
            models.CheckConstraint(
                condition=Q(ticket_cents__gt=0, ticket_cents__lte=1_000_000_000),
                name="draft_ticket_positive",
            ),
            models.CheckConstraint(
                condition=Q(budget_cents__gt=0, budget_cents__lte=1_000_000_000),
                name="draft_budget_positive",
            ),
            models.CheckConstraint(
                condition=Q(projected_paid_orders__gte=1, projected_paid_orders__lte=50000),
                name="draft_paid_orders_range",
            ),
        ]
