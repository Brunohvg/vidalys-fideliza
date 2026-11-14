"""Identidade omnichannel interna, independente de qualquer plataforma externa.

Contato verificado é indexado por HMAC (não pelo ID do canal). Carteiras
continuam pertencendo ao ProgramParticipant e nunca são migradas por lookup.
"""
import uuid

from django.db import models


class CustomerProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="customer_profiles"
    )
    # Pode existir sem adesão; não cria carteiras nem consentimento implícito.
    participant = models.OneToOneField(
        "participants.ProgramParticipant", on_delete=models.PROTECT,
        null=True, blank=True, related_name="customer_profile",
    )
    display_name = models.CharField(max_length=140, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "created_at"], name="cust_profile_tenant_idx"),
        ]


class VerifiedCustomerContact(models.Model):
    class Kind(models.TextChoices):
        EMAIL = "email", "E-mail"
        PHONE = "phone", "Telefone E.164"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    profile = models.ForeignKey(
        CustomerProfile, on_delete=models.PROTECT, related_name="verified_contacts"
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    # HMAC-SHA256 para não armazenar contato adicional em claro.
    lookup_digest = models.CharField(max_length=64)
    proof_method = models.CharField(max_length=32)
    verified_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "kind", "lookup_digest"],
                name="cust_verified_contact_once",
            ),
        ]


class ChannelCustomerReference(models.Model):
    """Vínculo de canal: um ID externo nunca transfere uma carteira entre perfis."""

    class Channel(models.TextChoices):
        NUVEMSHOP = "nuvemshop", "Nuvemshop"
        VIDALYS_FLOW = "vidalys_flow", "Vidalys Flow"
        COUNTER = "counter", "Balcão"
        WHATSAPP = "whatsapp", "WhatsApp"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    profile = models.ForeignKey(
        CustomerProfile, on_delete=models.PROTECT, related_name="channel_references"
    )
    channel = models.CharField(max_length=24, choices=Channel.choices)
    external_id = models.CharField(max_length=120)
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "channel", "external_id"],
                name="cust_channel_external_once",
            ),
        ]
