"""Resgate no site: opções da loja e cupom único por cliente. Só acrescenta."""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0011_credit_notice"),
        ("participants", "0009_member_birthday"),
    ]
    operations = [
        migrations.AddField(model_name="counterpilot", name="online_earning", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="counterpilot", name="online_coupons", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="counterpilot", name="coupon_combines", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="counterpilot", name="coupons_paused", field=models.BooleanField(default=False)),
        migrations.CreateModel(
            name="OnlineCoupon",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source", models.CharField(choices=[("giftback", "Crédito de giftback"), ("reward", "Recompensa de pontos")], max_length=10)),
                ("code", models.CharField(max_length=40, unique=True)),
                ("remote_id", models.CharField(blank=True, default="", max_length=40)),
                ("apply_url", models.URLField(blank=True, default="", max_length=300)),
                ("points", models.PositiveIntegerField()),
                ("discount_cents", models.PositiveIntegerField()),
                ("min_order_cents", models.PositiveIntegerField(default=0)),
                ("combines", models.BooleanField(default=False)),
                ("expires_at", models.DateTimeField()),
                ("allocations", models.JSONField(default=list)),
                ("state", models.CharField(choices=[("issuing", "Criando"), ("issued", "Disponível"), ("used", "Usado"), ("cancelled", "Cancelado"), ("expired", "Vencido"), ("failed", "Falhou")], default="issuing", max_length=10)),
                ("used_order_id", models.CharField(blank=True, default="", max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("settled_at", models.DateTimeField(blank=True, null=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
                ("participant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="online_coupons", to="participants.programparticipant")),
                ("reward", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="sales.discountrewarddraft")),
            ],
            options={
                "indexes": [models.Index(fields=["tenant", "state", "expires_at"], name="online_coupon_state_idx")],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("points__gt", 0)), name="online_coupon_points_positive"),
                    models.CheckConstraint(condition=models.Q(("discount_cents__gt", 0)), name="online_coupon_discount_positive"),
                ],
            },
        ),
    ]
