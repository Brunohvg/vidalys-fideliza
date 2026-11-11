"""Cadastro manual de custos por variante, sem sincronização ou alteração externa."""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class CostItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="cost_items")
    reference = models.CharField(max_length=100, help_text="Identificação local única por loja")
    sku = models.CharField(max_length=100, blank=True, default="")
    external_variant_id = models.CharField(max_length=64, blank=True, default="")
    name = models.CharField(max_length=180)
    unit_cost_cents = models.PositiveIntegerField(null=True, blank=True)
    selling_price_cents = models.PositiveIntegerField(null=True, blank=True)
    provenance = models.CharField(max_length=240, blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "reference"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "reference"], name="cost_tenant_reference_unique"),
            models.UniqueConstraint(
                fields=["tenant", "external_variant_id"],
                condition=~Q(external_variant_id=""),
                name="cost_tenant_variant_unique",
            ),
        ]

    @property
    def review_status(self):
        if self.unit_cost_cents is None:
            return "missing_cost"
        if self.verified_at is None:
            return "needs_review"
        if self.selling_price_cents is None:
            return "missing_price"
        return "ready_for_simulation"

    def snapshot(self):
        return {
            "reference": self.reference,
            "sku": self.sku,
            "external_variant_id": self.external_variant_id,
            "name": self.name,
            "unit_cost_cents": self.unit_cost_cents,
            "selling_price_cents": self.selling_price_cents,
            "provenance": self.provenance,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "version": self.version,
        }


class CostAudit(models.Model):
    """Histórico aditivo; sem interface de exclusão para operadores."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    item = models.ForeignKey(CostItem, on_delete=models.CASCADE, related_name="audits")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=12, choices=[("create", "Criação"), ("update", "Atualização")])
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
