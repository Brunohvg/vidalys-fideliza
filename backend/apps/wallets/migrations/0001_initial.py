"""Carteira interna em BRL e ledger aditivo; não importa nem concede cashback."""
import uuid
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True
    dependencies = [("tenants", "0001_initial"), ("participants", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="CashbackWallet",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("currency", models.CharField(default="BRL", editable=False, max_length=3)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("participant", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="cashback_wallet", to="participants.programparticipant",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="cashback_wallets", to="tenants.tenant",
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="CashbackEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(
                    max_length=24, choices=[
                        ("accrual", "Crédito pendente"), ("release", "Liberação"),
                        ("reserve", "Reserva"), ("cancel_reservation", "Cancelamento de reserva"),
                        ("redeem", "Resgate confirmado"), ("expire", "Expiração"),
                        ("reverse_pending", "Estorno pendente"),
                        ("reverse_available", "Estorno disponível"),
                    ],
                )),
                ("amount_cents", models.PositiveBigIntegerField()),
                ("idempotency_key", models.CharField(max_length=180)),
                ("source_order_id", models.CharField(blank=True, default="", max_length=80)),
                ("rule_version", models.CharField(max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("wallet", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="events", to="wallets.cashbackwallet",
                )),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="CashbackEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("bucket", models.CharField(
                    max_length=12, choices=[
                        ("pending", "Pendente"), ("available", "Liberado no ledger"),
                        ("reserved", "Reservado no ledger"),
                    ],
                )),
                ("delta_cents", models.BigIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("event", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="entries", to="wallets.cashbackevent",
                )),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="cashbackevent",
            constraint=models.UniqueConstraint(
                fields=("wallet", "idempotency_key"), name="cashback_wallet_idempotent_event",
            ),
        ),
        migrations.AddConstraint(
            model_name="cashbackevent",
            constraint=models.CheckConstraint(
                condition=Q(amount_cents__gt=0), name="cashback_event_positive_amount",
            ),
        ),
        migrations.AddConstraint(
            model_name="cashbackentry",
            constraint=models.UniqueConstraint(
                fields=("event", "bucket"), name="cashback_event_bucket_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="cashbackentry",
            constraint=models.CheckConstraint(
                condition=~Q(delta_cents=0), name="cashback_entry_nonzero",
            ),
        ),
    ]
