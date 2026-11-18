"""Aniversário (dia e mês) informado pelo próprio cliente no Meu Clube."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("participants", "0008_participant_phone")]
    operations = [
        migrations.AddField(model_name="enrollmentsubmission", name="birth_day",
                            field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="enrollmentsubmission", name="birth_month",
                            field=models.PositiveSmallIntegerField(blank=True, null=True)),
    ]
