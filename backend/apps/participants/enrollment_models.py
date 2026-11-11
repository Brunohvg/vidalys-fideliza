"""Convite e aceite registrados, ainda sem vincular uma compra/cliente Nuvemshop.

O solicitante do link não é considerado cliente verificado.
Nunca criar ProgramParticipant ou cashback neste módulo.
"""
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class ProgramTerms(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="loyalty_terms")
    version = models.CharField(max_length=40)
    title = models.CharField(max_length=100)
    body = models.TextField(max_length=4000)
    privacy_notice = models.TextField(max_length=2500, blank=True, default="")
    active = models.BooleanField(default=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                    on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-approved_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "version"],
                                    name="loyalty_terms_version_unique"),
            models.UniqueConstraint(fields=["tenant"], condition=Q(active=True),
                                    name="loyalty_single_active_terms"),
        ]


class EnrollmentInvite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="loyalty_invitations")
    terms = models.ForeignKey(ProgramTerms, on_delete=models.PROTECT,
                              related_name="invitations")
    token_digest = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name="+")
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class EnrollmentSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Aguardando verificação"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="loyalty_submissions")
    invitation = models.OneToOneField(EnrollmentInvite, on_delete=models.PROTECT,
                                      related_name="submission")
    terms = models.ForeignKey(ProgramTerms, on_delete=models.PROTECT,
                              related_name="submissions")
    name = models.CharField(max_length=140)
    email = models.EmailField(max_length=254)
    terms_digest = models.CharField(max_length=64)
    accepted_at = models.DateTimeField()
    marketing_opt_in = models.BooleanField(default=False)
    status = models.CharField(max_length=32, choices=Status.choices,
                              default=Status.PENDING_VERIFICATION)

    class Meta:
        ordering = ["-accepted_at", "-id"]
