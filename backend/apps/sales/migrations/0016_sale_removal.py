"""Remoção de venda lançada à mão (soft delete auditado). Só acrescenta."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sales", "0015_counter_channel"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="salerecord", name="removed_at",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="salerecord", name="removed_by",
                            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                                    related_name="+", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="salerecord", name="removed_reason",
                            field=models.CharField(blank=True, default="", max_length=240)),
    ]
