"""Celular do participante como HMAC por loja + 4 últimos dígitos.

Só adiciona colunas com valor padrão vazio e uma restrição parcial:
não altera nem apaga dados existentes.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("participants", "0007_standalone_participant")]
    operations = [
        migrations.AddField(
            model_name="programparticipant", name="phone_digest",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="programparticipant", name="phone_last4",
            field=models.CharField(max_length=4, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="enrollmentsubmission", name="phone_digest",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="enrollmentsubmission", name="phone_last4",
            field=models.CharField(max_length=4, blank=True, default=""),
        ),
        migrations.AddConstraint(
            model_name="programparticipant",
            constraint=models.UniqueConstraint(
                fields=["tenant", "phone_digest"],
                condition=~models.Q(phone_digest=""),
                name="participant_phone_once",
            ),
        ),
    ]
