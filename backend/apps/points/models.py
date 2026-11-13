"""Ledger de pontos inteiros, sem relação contábil com o cashback em BRL.

Os eventos e lançamentos são append-only na camada de domínio. Não há
endpoints públicos para escrita. Migrações não concedem pontos.
"""
import uuid
from django.db import models
from django.db.models import Q


class PointWallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="point_wallets"
    )
    participant = models.OneToOneField(
        "participants.ProgramParticipant", on_delete=models.PROTECT,
        related_name="point_wallet",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class PointLot(models.Model):
    """Uma única compra e regra aplicada; identidade do pedido não se repete."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    wallet = models.ForeignKey(
        PointWallet, on_delete=models.PROTECT, related_name="lots"
    )
    channel = models.CharField(max_length=24)
    source_reference = models.CharField(max_length=80)
    eligible_amount_cents = models.PositiveBigIntegerField()
    source_paid_at = models.DateTimeField()
    verification_digest = models.CharField(max_length=64)
    rule_version = models.CharField(max_length=40)
    points_issued = models.PositiveBigIntegerField()
    unlock_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "channel", "source_reference"],
                name="points_tenant_channel_order_once",
            ),
            models.CheckConstraint(
                condition=Q(points_issued__gt=0),
                name="point_lot_positive_issued",
            ),
            models.CheckConstraint(
                condition=Q(eligible_amount_cents__gt=0),
                name="point_lot_positive_amount",
            ),
        ]
        indexes = [
            models.Index(fields=["wallet", "expires_at"], name="point_lot_expiration_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Lote de pontos é imutável.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Lote de pontos não pode ser excluído.")


class PointEvent(models.Model):
    class Kind(models.TextChoices):
        ACCRUE = "accrue", "Compra elegível registrada"
        RELEASE = "release", "Pontos liberados"
        RESERVE = "reserve", "Reserva interna"
        CANCEL_RESERVE = "cancel_reserve", "Reserva cancelada"
        REDEEM = "redeem", "Resgate confirmado"
        REVERSE_PENDING = "reverse_pending", "Compra estornada antes da liberação"
        REVERSE_AVAILABLE = "reverse_available", "Compra estornada após liberação"
        EXPIRE_PENDING = "expire_pending", "Pontos pendentes expirados"
        EXPIRE_AVAILABLE = "expire_available", "Pontos disponíveis expirados"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lot = models.ForeignKey(PointLot, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=28, choices=Kind.choices)
    amount = models.PositiveBigIntegerField()
    idempotency_key = models.CharField(max_length=180)
    external_receipt = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lot", "idempotency_key"], name="points_event_idempotency"
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="points_event_positive_amount"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Eventos de pontos são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Eventos de pontos não podem ser excluídos.")


class PointEntry(models.Model):
    class Bucket(models.TextChoices):
        PENDING = "pending", "Pendente"
        AVAILABLE = "available", "Disponível"
        RESERVED = "reserved", "Reservado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        PointEvent, on_delete=models.PROTECT, related_name="entries"
    )
    bucket = models.CharField(max_length=12, choices=Bucket.choices)
    delta = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "bucket"], name="points_event_bucket_once"
            ),
            models.CheckConstraint(
                condition=~Q(delta=0), name="point_entry_nonzero"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Lançamentos de pontos são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Lançamentos de pontos não podem ser excluídos.")
