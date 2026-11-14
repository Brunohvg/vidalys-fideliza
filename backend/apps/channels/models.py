"""Credenciais individuais para canais servidor-a-servidor; segredo nunca em claro."""
import uuid

from django.db import models


class ChannelCredential(models.Model):
    class Channel(models.TextChoices):
        VIDALYS_FLOW = "vidalys_flow", "Vidalys Flow"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="channel_credentials"
    )
    channel = models.CharField(max_length=24, choices=Channel.choices)
    label = models.CharField(max_length=80)
    key_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "channel"], name="channel_key_tenant_idx"),
        ]
