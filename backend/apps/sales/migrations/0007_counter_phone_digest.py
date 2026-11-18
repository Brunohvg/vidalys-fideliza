"""Celular (HMAC por loja) de venda de balcão ainda sem cliente do clube.

Só adiciona uma coluna com valor padrão vazio: não altera dados existentes.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0006_counter_identity_link"),
        ("participants", "0008_participant_phone"),
    ]
    operations = [
        migrations.AddField(
            model_name="salerecord", name="counter_phone_digest",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
    ]
