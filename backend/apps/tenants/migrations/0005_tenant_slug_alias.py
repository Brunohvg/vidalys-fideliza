"""Endereços antigos do clube. Só cria uma tabela nova; não altera dados."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tenants", "0004_loyalty_live_optin")]
    operations = [
        migrations.CreateModel(
            name="TenantSlugAlias",
            fields=[
                ("slug", models.SlugField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="slug_aliases", to="tenants.tenant",
                )),
            ],
        ),
    ]
