"""Modo do programa (pontos ou giftback) por loja; vale de balcão pode ser crédito sem recompensa.
Só cria tabela nova e torna um campo opcional; nenhum dado existente muda."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0009_counter_pilot"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(
            model_name="counterredemption", name="reward",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="sales.discountrewarddraft"),
        ),
        migrations.CreateModel(
            name="ProgramMode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("points", "Pontos"), ("giftback", "Giftback")], default="points", max_length=10)),
                ("giftback_bps", models.PositiveIntegerField(default=1000)),
                ("giftback_cap_cents", models.PositiveIntegerField(default=2000)),
                ("giftback_min_order_cents", models.PositiveIntegerField(default=8000)),
                ("giftback_validity_days", models.PositiveSmallIntegerField(default=30)),
                ("giftback_hold_days", models.PositiveSmallIntegerField(default=7)),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="program_mode", to="tenants.tenant")),
                ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="program_modes", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [
                models.CheckConstraint(condition=models.Q(("giftback_bps__gte", 100), ("giftback_bps__lte", 3000)), name="program_mode_bps_range"),
                models.CheckConstraint(condition=models.Q(("giftback_cap_cents__gt", 0)), name="program_mode_cap_positive"),
                models.CheckConstraint(condition=models.Q(("giftback_validity_days__gte", 7)), name="program_mode_validity_min"),
            ]},
        ),
    ]
