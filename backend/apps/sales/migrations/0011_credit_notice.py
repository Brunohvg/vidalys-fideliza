"""Avisos de saldo liberado/vencendo: um por lote e tipo. Só cria tabela nova."""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0010_program_mode"),
        ("points", "0002_immutable_postgres_ledger"),
    ]
    operations = [
        migrations.CreateModel(
            name="CreditNotice",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(choices=[("released", "Liberado"), ("expiring", "Vencendo")], max_length=10)),
                ("emailed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant")),
                ("lot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notices", to="points.pointlot")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("lot", "kind"), name="credit_notice_once_per_lot")]},
        ),
    ]
