"""PR26: registrar modo e hash da evidência de autorização sem retroativar lojas."""
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("tenants", "0004_loyalty_live_optin")]
    operations = [
        migrations.AddField(model_name="tenantloyaltyactivationaudit", name="mode",
            field=models.CharField(max_length=12, default="qa")),
        migrations.AddField(model_name="tenantloyaltyactivationaudit", name="gates_digest",
            field=models.CharField(max_length=64, blank=True, default="")),
    ]
