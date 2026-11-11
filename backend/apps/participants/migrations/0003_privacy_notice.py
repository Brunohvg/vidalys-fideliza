"""Adicionar texto de transparência e origem da solicitação pública."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("participants", "0002_enrollment_terms_invites")]
    operations = [
        migrations.AddField(
            model_name="programterms",
            name="privacy_notice",
            field=models.TextField(max_length=2500, blank=True, default=""),
        ),
    ]
