# Fundação multi-tenant, sem importação de dados reais.
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Tenant", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("name", models.CharField(max_length=140)),
            ("slug", models.SlugField(unique=True)),
            ("platform", models.CharField(default="nuvemshop", max_length=32)),
            ("external_store_id", models.CharField(blank=True, max_length=64, null=True)),
            ("status", models.CharField(choices=[("draft", "Rascunho"), ("active", "Ativa"), ("suspended", "Suspensa")], default="draft", max_length=16)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
        ], options={"ordering": ["name"]}),
        migrations.CreateModel(name="TenantMembership", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("role", models.CharField(choices=[("owner", "Proprietário"), ("admin", "Administrador"), ("analyst", "Analista")], max_length=16)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="tenants.tenant")),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tenant_memberships", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.AddConstraint(model_name="tenant", constraint=models.UniqueConstraint(fields=("platform", "external_store_id"), name="unique_tenant_platform_store")),
        migrations.AddConstraint(model_name="tenantmembership", constraint=models.UniqueConstraint(fields=("tenant", "user"), name="unique_tenant_member")),
    ]
