"""Ledger de cashback em centavos; escrita apenas pelo serviço interno controlado.

Nunca usar estes modelos como comprovação de pagamento, entrega ou resgate no checkout.
"""
import uuid

from django.db import models
from django.db.models import Q


class CashbackWallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="cashback_wallets"
    )
    participant = models.OneToOneField(
        "participants.ProgramParticipant", on_delete=models.PROTECT,
        related_name="cashback_wallet",
    )
    currency = models.CharField(max_length=3, default="BRL", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class CashbackEvent(models.Model):
    """Um evento com chave idempotente; contém uma ou duas entradas imutáveis."""
    class Kind(models.TextChoices):
        ACCRUAL = "accrual", "Crédito pendente"
        RELEASE = "release", "Liberação"
        RESERVE = "reserve", "Reserva"
        CANCEL_RESERVATION = "cancel_reservation", "Cancelamento de reserva"
        REDEEM = "redeem", "Resgate confirmado"
        EXPIRE = "expire", "Expiração"
        REVERSE_PENDING = "reverse_pending", "Estorno pendente"
        REVERSE_AVAILABLE = "reverse_available", "Estorno disponível"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(CashbackWallet, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    amount_cents = models.PositiveBigIntegerField()
    idempotency_key = models.CharField(max_length=180)
    source_order_id = models.CharField(max_length=80, blank=True, default="")
    rule_version = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["wallet", "idempotency_key"],
                name="cashback_wallet_idempotent_event",
            ),
            models.CheckConstraint(
                condition=Q(amount_cents__gt=0),
                name="cashback_event_positive_amount",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Eventos do ledger não podem ser alterados.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Eventos do ledger não podem ser excluídos.")


class CashbackEntry(models.Model):
    """Movimento assinado em um bucket; saldo é a soma de lançamentos."""
    class Bucket(models.TextChoices):
        PENDING = "pending", "Pendente"
        AVAILABLE = "available", "Liberado no ledger"
        RESERVED = "reserved", "Reservado no ledger"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(CashbackEvent, on_delete=models.PROTECT, related_name="entries")
    bucket = models.CharField(max_length=12, choices=Bucket.choices)
    delta_cents = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "bucket"],
                name="cashback_event_bucket_unique",
            ),
            models.CheckConstraint(
                condition=~Q(delta_cents=0),
                name="cashback_entry_nonzero",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Lançamentos do ledger não podem ser alterados.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Lançamentos do ledger não podem ser excluídos.")
