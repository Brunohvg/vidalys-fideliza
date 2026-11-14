"""Versões de programa, decisões verificáveis, vouchers e pendências de recuperação.

Não recria as carteiras de points/wallets. Não armazena token de cupom em claro.
Nenhuma destas tabelas cria benefícios ou confirma um PSP automaticamente.
"""
import uuid

from django.db import models
from django.db.models import Q


class LoyaltyRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="loyalty_rules")
    version = models.PositiveIntegerField()
    enabled = models.BooleanField(default=False)
    points_per_unit = models.PositiveIntegerField(default=1)
    points_per_cents = models.PositiveIntegerField(default=100)
    cashback_bps = models.PositiveSmallIntegerField(default=0)
    # Custo potencial de cada ponto para reservar margem/orçamento.
    point_value_cents = models.PositiveIntegerField(default=1)
    hold_days = models.PositiveSmallIntegerField(default=7)
    validity_days = models.PositiveSmallIntegerField(default=180)
    minimum_margin_bps = models.PositiveSmallIntegerField(default=1000)
    budget_cents = models.PositiveBigIntegerField()
    second_purchase_window_days = models.PositiveSmallIntegerField(default=15)
    second_purchase_multiplier_bps = models.PositiveIntegerField(default=10000)
    winback_after_days = models.PositiveSmallIntegerField(default=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "version"], name="loyalty_rule_version_once"),
            models.UniqueConstraint(
                fields=["tenant"], condition=Q(enabled=True), name="loyalty_single_enabled_rule",
            ),
            models.CheckConstraint(
                condition=Q(points_per_cents__gte=1), name="loyalty_points_base_positive",
            ),
            models.CheckConstraint(
                condition=Q(cashback_bps__lte=10000), name="loyalty_cashback_max",
            ),
            models.CheckConstraint(
                condition=Q(minimum_margin_bps__lte=10000), name="loyalty_min_margin_max",
            ),
            models.CheckConstraint(
                condition=Q(budget_cents__gt=0), name="loyalty_budget_positive",
            ),
            models.CheckConstraint(
                condition=Q(second_purchase_multiplier_bps__gte=10000),
                name="loyalty_second_multiplier_min",
            ),
        ]


class LoyaltyTier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(LoyaltyRule, on_delete=models.PROTECT, related_name="tiers")
    name = models.CharField(max_length=40)
    minimum_spend_cents = models.PositiveBigIntegerField()
    multiplier_bps = models.PositiveIntegerField(default=10000)

    class Meta:
        ordering = ["minimum_spend_cents", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "minimum_spend_cents"], name="loyalty_tier_threshold_once",
            ),
            models.CheckConstraint(
                condition=Q(multiplier_bps__gte=10000, multiplier_bps__lte=30000),
                name="loyalty_tier_multiplier_range",
            ),
        ]


class FinancialEvidence(models.Model):
    """Prova normalizada por adaptador PSP confiável, ainda NÃO conectado.

    Inserir linhas por si só não comprova PSP. O executor sempre verifica flags
    e origem autorizada; a integração real pertence ao gate G7.
    """

    class Kind(models.TextChoices):
        CAPTURE = "capture", "Captura"
        REFUND = "refund", "Estorno ou cancelamento confirmado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    sale = models.ForeignKey("sales.SaleRecord", on_delete=models.PROTECT, related_name="payment_evidence")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    provider = models.CharField(max_length=48)
    external_event_id = models.CharField(max_length=100)
    amount_cents = models.PositiveBigIntegerField()
    verification_digest = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    verified_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "external_event_id"],
                name="loyalty_evidence_event_once",
            ),
            models.CheckConstraint(
                condition=Q(amount_cents__gt=0), name="loyalty_evidence_amount_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Comprovação financeira é imutável.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Comprovação financeira não pode ser removida.")


class LoyaltyGrant(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Crédito pendente"
        RELEASED = "released", "Disponível"
        REVERSED = "reversed", "Revertido"
        RECOVERY = "recovery", "Recuperação pendente"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    sale = models.OneToOneField(
        "sales.SaleRecord", on_delete=models.PROTECT, related_name="loyalty_grant",
    )
    participant = models.ForeignKey("participants.ProgramParticipant", on_delete=models.PROTECT)
    rule = models.ForeignKey(LoyaltyRule, on_delete=models.PROTECT)
    evidence = models.OneToOneField(FinancialEvidence, on_delete=models.PROTECT)
    point_lot = models.OneToOneField(
        "points.PointLot", on_delete=models.PROTECT, null=True, blank=True,
    )
    cashback_event = models.OneToOneField(
        "wallets.CashbackEvent", on_delete=models.PROTECT, null=True, blank=True,
    )
    points_issued = models.PositiveBigIntegerField(default=0)
    cashback_cents = models.PositiveBigIntegerField(default=0)
    exposure_cents = models.PositiveBigIntegerField()
    eligible_amount_cents = models.PositiveBigIntegerField()
    captured_at = models.DateTimeField()
    unlock_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reversed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MemberTierSnapshot(models.Model):
    participant = models.OneToOneField(
        "participants.ProgramParticipant", on_delete=models.PROTECT,
        primary_key=True, related_name="tier_snapshot",
    )
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    rule = models.ForeignKey(LoyaltyRule, on_delete=models.PROTECT)
    tier = models.ForeignKey(LoyaltyTier, on_delete=models.PROTECT)
    rolling_spend_cents = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class LoyaltyRecovery(models.Model):
    """Passivo explícito se benefício já foi gasto e não pode ser debitado."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grant = models.OneToOneField(LoyaltyGrant, on_delete=models.PROTECT)
    evidence = models.OneToOneField(FinancialEvidence, on_delete=models.PROTECT)
    remaining_points = models.PositiveBigIntegerField(default=0)
    remaining_cashback_cents = models.PositiveBigIntegerField(default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


class LoyaltyVoucher(models.Model):
    class Unit(models.TextChoices):
        POINTS = "points", "Pontos"
        CASHBACK = "cashback", "Cashback em centavos"

    class State(models.TextChoices):
        RESERVED = "reserved", "Reservado"
        REDEEMED = "redeemed", "Resgatado"
        CANCELLED = "cancelled", "Cancelado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    participant = models.ForeignKey("participants.ProgramParticipant", on_delete=models.PROTECT)
    rule = models.ForeignKey(LoyaltyRule, on_delete=models.PROTECT)
    code_digest = models.CharField(max_length=64, unique=True)
    unit = models.CharField(max_length=8, choices=Unit.choices)
    amount = models.PositiveBigIntegerField()
    discount_cents = models.PositiveBigIntegerField()
    state = models.CharField(max_length=12, choices=State.choices, default=State.RESERVED)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redemption_channel = models.CharField(max_length=24, blank=True, default="")
    redemption_reference = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="loyalty_voucher_positive_amount"),
            models.CheckConstraint(condition=Q(discount_cents__gt=0), name="loyalty_voucher_positive_discount"),
            models.UniqueConstraint(
                fields=["tenant", "redemption_channel", "redemption_reference"],
                condition=~Q(redemption_reference=""),
                name="loyalty_voucher_redemption_once",
            ),
        ]


class VoucherPointAllocation(models.Model):
    voucher = models.ForeignKey(
        LoyaltyVoucher, on_delete=models.PROTECT, related_name="point_allocations",
    )
    lot = models.ForeignKey("points.PointLot", on_delete=models.PROTECT)
    amount = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["voucher", "lot"], name="loyalty_voucher_lot_once"),
        ]


class LoyaltyEngagement(models.Model):
    """Elegibilidade de missões e winback; notificação não credita pontos."""

    class Kind(models.TextChoices):
        PROFILE = "profile", "Perfil verificado"
        BIRTHDAY = "birthday", "Aniversário"
        WINBACK = "winback", "Reativação"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    participant = models.ForeignKey("participants.ProgramParticipant", on_delete=models.PROTECT)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    period_key = models.CharField(max_length=16)
    eligible_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "participant", "kind", "period_key"],
                name="loyalty_engagement_once",
            ),
        ]
