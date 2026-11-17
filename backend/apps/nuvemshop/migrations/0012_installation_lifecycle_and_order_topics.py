"""Ciclo de vida da instalação (app/uninstalled) e avisos de cancelamento.

Somente metadados: nenhuma coluna nova guarda dado pessoal ou valor.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nuvemshop", "0011_coupon_ownership_incident")]
    operations = [
        migrations.AddField(
            model_name="nuvemshopinstallation",
            name="uninstalled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="orderwebhookevent",
            name="topic",
            field=models.CharField(
                max_length=24,
                choices=[
                    ("order/paid", "Pagamento reportado"),
                    ("order/updated", "Pedido alterado"),
                    ("order/cancelled", "Pedido cancelado"),
                    ("order/voided", "Pagamento anulado"),
                ],
            ),
        ),
    ]
