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
