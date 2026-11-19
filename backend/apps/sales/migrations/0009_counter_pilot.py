"""Piloto de pontos no balcão: configuração por loja e vales usados no caixa.
Só cria tabelas novas; nenhum dado existente é alterado."""
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0008_smart_point_campaigns"),
        ("tenants", "0005_tenant_slug_alias"),
        ("participants", "0009_member_birthday"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="CounterPilot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("active", models.BooleanField(default=False)),
                ("per_sale_cap_points", models.PositiveIntegerField(default=1500)),
                ("budget_points", models.PositiveIntegerField(default=50000)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("paused_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="counter_pilot", to="tenants.tenant")),
                ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="counter_pilots", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [
                models.CheckConstraint(condition=models.Q(("per_sale_cap_points__gt", 0)), name="counter_pilot_cap_positive"),
                models.CheckConstraint(condition=models.Q(("budget_points__gt", 0)), name="counter_pilot_budget_positive"),
            ]},
        ),
        migrations.CreateModel(
            name="CounterRedemption",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("points", models.PositiveIntegerField()),
                ("discount_cents", models.PositiveIntegerField()),
                ("allocations", models.JSONField(default=list)),
                ("state", models.CharField(choices=[("reserved", "Reservado"), ("redeemed", "Usado"), ("cancelled", "Devolvido")], default="reserved", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("settled_at", models.DateTimeField(blank=True, null=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
                ("sale", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="counter_redemption", to="sales.salerecord")),
                ("participant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="participants.programparticipant")),
                ("reward", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="sales.discountrewarddraft")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="counter_redemptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [
                models.CheckConstraint(condition=models.Q(("points__gt", 0)), name="counter_redemption_points_positive"),
                models.CheckConstraint(condition=models.Q(("discount_cents__gt", 0)), name="counter_redemption_discount_positive"),
            ]},
        ),
    ]
