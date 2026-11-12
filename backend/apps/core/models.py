"""Identidades dos lojistas, separadas dos cadastros de clientes dos programas."""
import uuid

from django.conf import settings
from django.db import models


class MerchantEmailIdentity(models.Model):
    """Um e-mail confirmado não pode pertencer a dois lojistas."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="merchant_email_identity")
    normalized_email = models.EmailField(max_length=254, unique=True)
    verified_at = models.DateTimeField()


class MerchantRegistration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    normalized_email = models.EmailField(max_length=254, unique=True)
    first_name = models.CharField(max_length=100)
    store_name = models.CharField(max_length=140)
    password_hash = models.CharField(max_length=256)
    requested_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)


class MerchantPasswordReset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="merchant_password_resets")
    email_snapshot = models.EmailField(max_length=254)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MerchantEmailClaim(models.Model):
    """Um dono por caixa postal canônica (inclui aliases conhecidos do Gmail).

    Guarda atômica no PostgreSQL: duas confirmações concorrentes nunca
    conseguem criar dois lojistas para a mesma caixa postal.
    """
    canonical_email = models.EmailField(max_length=254, unique=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="merchant_email_claim")
    created_at = models.DateTimeField(auto_now_add=True)
