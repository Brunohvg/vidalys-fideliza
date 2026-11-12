"""Evidência agregada da sanitização, sem armazenar dados pessoais."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nuvemshop", "0003_privacy_delivery_evidence")]

    operations = [
        migrations.AddField(
            model_name="privacywebhookrequest", name="sanitized_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="privacywebhookrequest", name="sanitization_summary",
            field=models.JSONField(default=dict, blank=True),
        ),
    ]
