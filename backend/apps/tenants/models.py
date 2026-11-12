import uuid
from django.conf import settings
from django.db import models

class Tenant(models.Model):
    """Loja isolada. Não há sincronização automática no scaffold."""
    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        ACTIVE = "active", "Ativa"
        SUSPENDED = "suspended", "Suspensa"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=140)
    slug = models.SlugField(unique=True)
    # O canal é independente até existir instalação OAuth autorizada.
    platform = models.CharField(max_length=32, default="independent")
    external_store_id = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(
            fields=["platform", "external_store_id"],
            name="unique_tenant_platform_store",
        )]

    def __str__(self):
        return self.name

class TenantMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Proprietário"
        ADMIN = "admin", "Administrador"
        ANALYST = "analyst", "Analista"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tenant_memberships")
    role = models.CharField(max_length=16, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "user"], name="unique_tenant_member")]

# Importados para reconhecimento do Django e migrações.
from .branding_models import TenantBranding, TenantBrandingAudit  # noqa: E402,F401
