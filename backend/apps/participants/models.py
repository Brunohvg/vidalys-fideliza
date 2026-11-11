"""Adesão explícita ao programa, distinta da base de clientes da loja.

Sem integração de clientes e sem fluxo de consentimento publicado ainda,
este modelo permanece vazio. Não há geração automática de membros.
"""
import uuid

from django.db import models


class ProgramParticipant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Participando"
        PAUSED = "paused", "Pausado"
        WITHDRAWN = "withdrawn", "Adesão encerrada"

    class ConsentChannel(models.TextChoices):
        CUSTOMER_PORTAL = "customer_portal", "Portal do participante"
        STOREFRONT_OPT_IN = "storefront_opt_in", "Aceite na vitrine"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="program_participants")
    # Referência externa só pode ser definida por fluxo de adesão futuro validado.
    external_customer_id = models.CharField(max_length=64)
    display_name = models.CharField(max_length=140, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    consent_at = models.DateTimeField()
    consent_channel = models.CharField(max_length=32, choices=ConsentChannel.choices)
    terms_version = models.CharField(max_length=40)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    joined_at = models.DateTimeField(auto_now_add=True)
    # Atividade do programa, não da loja; null significa não apurado.
    last_program_activity_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-joined_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_customer_id"],
                name="loyalty_tenant_customer_unique",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "joined_at"], name="loyalty_tenant_member_idx"),
        ]
