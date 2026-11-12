"""Permite webhook de pedido sem event_launch_ts, conforme contrato do provedor."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nuvemshop", "0005_order_webhook_events")]

    operations = [
        migrations.AlterField(
            model_name="orderwebhookevent",
            name="event_launch_ts",
            field=models.BigIntegerField(null=True, blank=True),
        ),
    ]
