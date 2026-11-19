"""Modo de operação por loja (teste/comercial), liberado só por superusuário. Só acrescenta."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0013_coupon_uncertain"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name="counterpilot", name="operation_mode",
            field=models.CharField(choices=[("test", "Teste"), ("commercial", "Comercial")], default="test", max_length=12),
        ),
        migrations.AddField(model_name="counterpilot", name="commercial_at",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="counterpilot", name="commercial_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="+", to=settings.AUTH_USER_MODEL),
        ),
    ]
