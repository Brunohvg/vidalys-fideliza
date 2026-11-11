"""Branding multi-tenant e histórico por versão, sem publicação automática."""
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="TenantBranding",
            fields=[
                ("tenant", models.OneToOneField(to="tenants.tenant", primary_key=True,
                    serialize=False, on_delete=django.db.models.deletion.CASCADE,
                    related_name="branding")),
                ("program_name", models.CharField(max_length=80, default="", blank=True)),
                ("primary_color", models.CharField(max_length=7, default="#087F79")),
                ("accent_color", models.CharField(max_length=7, default="#37D5BB")),
                ("support_email", models.EmailField(max_length=254, default="", blank=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.SET_NULL, null=True, related_name="+")),
            ],
        ),
        migrations.CreateModel(
            name="TenantBrandingAudit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                    primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("before", models.JSONField()),
                ("after", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name="+")),
                ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=
                    django.db.models.deletion.CASCADE, related_name="branding_history")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="tenantbrandingaudit",
            constraint=models.UniqueConstraint(fields=["tenant", "version"],
                name="tenant_branding_audit_version_unique"),
        ),
    ]
