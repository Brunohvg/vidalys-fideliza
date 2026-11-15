"""Termos explícitos da recompensa, independente de resgates ativos."""
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("sales", "0004_channel_order_ingestion")]
    operations = [
        migrations.AddField(model_name="discountrewarddraft", name="redemption_unit",
            field=models.CharField(max_length=8, choices=[
                ("points", "Pontos"), ("cashback", "Cashback (centavos)"),
            ], default="points")),
        migrations.AddField(model_name="discountrewarddraft", name="valid_from",
            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="discountrewarddraft", name="expires_at",
            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="discountrewarddraft", name="allowed_channels",
            field=models.CharField(max_length=100, default="counter,vidalys_flow")),
    ]
