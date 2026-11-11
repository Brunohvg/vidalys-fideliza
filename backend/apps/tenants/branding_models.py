"""Identidade pública configurável, versionada e isolada por lojista.

Não publica programa, domínios ou benefícios automaticamente.
"""
import uuid
from django.conf import settings
from django.db import models


class TenantBranding(models.Model):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE,
                                  primary_key=True, related_name="branding")
    program_name = models.CharField(max_length=80, default="", blank=True)
    primary_color = models.CharField(max_length=7, default="#087F79")
    accent_color = models.CharField(max_length=7, default="#37D5BB")
    support_email = models.EmailField(max_length=254, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)


class TenantBrandingAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="branding_history")
    version = models.PositiveIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                              on_delete=models.SET_NULL, related_name="+")
    before = models.JSONField()
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "version"],
                                    name="tenant_branding_audit_version_unique"),
        ]
