"""PR25: loja piloto nunca é ativada por instalação OAuth ou migração."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0003_unconnected_merchant_tenants"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name="tenant", name="loyalty_live_enabled",
            field=models.BooleanField(default=False)),
        migrations.CreateModel(
            name="TenantLoyaltyActivationAudit",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("before_enabled", models.BooleanField()),
                ("after_enabled", models.BooleanField()),
                ("approved_sha", models.CharField(max_length=40)),
                ("ticket", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    related_name="loyalty_activation_history",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("actor", models.ForeignKey(to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
    ]
