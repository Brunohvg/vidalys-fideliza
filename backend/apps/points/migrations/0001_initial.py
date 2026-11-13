"""Carteira de pontos inteiros sem qualquer crédito na migração."""
import uuid
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("participants", "0007_standalone_participant"),
        ("tenants", "0003_unconnected_merchant_tenants"),
    ]

    operations = [
        migrations.CreateModel(
            name="PointWallet",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                         editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="point_wallets")),
                ("participant", models.OneToOneField(
                    to="participants.programparticipant",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="point_wallet")),
            ],
        ),
        migrations.CreateModel(
            name="PointLot",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                         editable=False, serialize=False)),
                ("channel", models.CharField(max_length=24)),
                ("source_reference", models.CharField(max_length=80)),
                ("eligible_amount_cents", models.PositiveBigIntegerField()),
                ("source_paid_at", models.DateTimeField()),
                ("verification_digest", models.CharField(max_length=64)),
                ("rule_version", models.CharField(max_length=40)),
                ("points_issued", models.PositiveBigIntegerField()),
                ("unlock_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("wallet", models.ForeignKey(to="points.pointwallet",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="lots")),
            ],
            options={"indexes":[models.Index(
                fields=["wallet","expires_at"],
                name="point_lot_expiration_idx"
            )]},
        ),
        migrations.CreateModel(
            name="PointEvent",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                         editable=False, serialize=False)),
                ("kind", models.CharField(max_length=28, choices=[
                    ("accrue","Compra elegível registrada"),
                    ("release","Pontos liberados"),
                    ("reserve","Reserva interna"),
                    ("cancel_reserve","Reserva cancelada"),
                    ("redeem","Resgate confirmado"),
                    ("reverse_pending","Compra estornada antes da liberação"),
                    ("reverse_available","Compra estornada após liberação"),
                    ("expire_pending","Pontos pendentes expirados"),
                    ("expire_available","Pontos disponíveis expirados"),
                ])),
                ("amount", models.PositiveBigIntegerField()),
                ("idempotency_key", models.CharField(max_length=180)),
                ("external_receipt", models.CharField(max_length=100,blank=True,default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("lot", models.ForeignKey(to="points.pointlot",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="events")),
            ],
            options={"ordering":["-created_at","-id"]},
        ),
        migrations.CreateModel(
            name="PointEntry",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                                         editable=False, serialize=False)),
                ("bucket", models.CharField(max_length=12, choices=[
                    ("pending","Pendente"),("available","Disponível"),
                    ("reserved","Reservado")
                ])),
                ("delta", models.BigIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("event", models.ForeignKey(to="points.pointevent",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="entries")),
            ],
        ),
        migrations.AddConstraint(model_name="pointlot",constraint=models.UniqueConstraint(
            fields=["tenant","channel","source_reference"],
            name="points_tenant_channel_order_once")),
        migrations.AddConstraint(model_name="pointlot",constraint=models.CheckConstraint(
            condition=Q(points_issued__gt=0),name="point_lot_positive_issued")),
        migrations.AddConstraint(model_name="pointlot",constraint=models.CheckConstraint(
            condition=Q(eligible_amount_cents__gt=0),name="point_lot_positive_amount")),
        migrations.AddConstraint(model_name="pointevent",constraint=models.UniqueConstraint(
            fields=["lot","idempotency_key"],name="points_event_idempotency")),
        migrations.AddConstraint(model_name="pointevent",constraint=models.CheckConstraint(
            condition=Q(amount__gt=0),name="points_event_positive_amount")),
        migrations.AddConstraint(model_name="pointentry",constraint=models.UniqueConstraint(
            fields=["event","bucket"],name="points_event_bucket_once")),
        migrations.AddConstraint(model_name="pointentry",constraint=models.CheckConstraint(
            condition=~Q(delta=0),name="point_entry_nonzero")),
    ]
