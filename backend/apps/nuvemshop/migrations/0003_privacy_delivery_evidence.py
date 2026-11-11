"""Metadados mínimos de relatório de privacidade, sem guardar conteúdo pessoal."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("nuvemshop", "0002_privacy_requests"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name="privacywebhookrequest", name="customer_email_digest",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="privacywebhookrequest", name="report_digest",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="privacywebhookrequest", name="report_accessed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="privacywebhookrequest", name="report_accessed_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL, null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
            ),
        ),
        migrations.AddField(
            model_name="privacywebhookrequest", name="delivery_confirmed_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL, null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
            ),
        ),
    ]
