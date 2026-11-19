"""Tópico de reconciliação: pedido achado pela busca da cliente sem webhook recebido."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nuvemshop", "0011_coupon_ownership_incident")]
    operations = [
        migrations.AlterField(
            model_name="orderwebhookevent",
            name="topic",
            field=models.CharField(max_length=24, choices=[
                ("order/paid", "Pagamento reportado"),
                ("order/updated", "Pedido alterado"),
                ("reconcile/backfill", "Reconciliação (sem webhook)"),
            ]),
        ),
    ]
