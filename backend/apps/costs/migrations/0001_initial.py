# First cost registry migration; no external data import.
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="CostItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(help_text="Identificação local única por loja", max_length=100)),
                ("sku", models.CharField(blank=True, default="", max_length=100)),
                ("external_variant_id", models.CharField(blank=True, default="", max_length=64)),
                ("name", models.CharField(max_length=180)),
                ("unit_cost_cents", models.PositiveIntegerField(blank=True, null=True)),
                ("selling_price_cents", models.PositiveIntegerField(blank=True, null=True)),
                ("provenance", models.CharField(blank=True, default="", max_length=240)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cost_items", to="tenants.tenant")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name", "reference"]},
        ),
        migrations.CreateModel(
            name="CostAudit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(choices=[("create", "Criação"), ("update", "Atualização")], max_length=12)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tenants.tenant")),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audits", to="costs.costitem")),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="costitem",
            constraint=models.UniqueConstraint(fields=("tenant", "reference"), name="cost_tenant_reference_unique"),
        ),
        migrations.AddConstraint(
            model_name="costitem",
            constraint=models.UniqueConstraint(
                condition=~Q(external_variant_id=""),
                fields=("tenant", "external_variant_id"),
                name="cost_tenant_variant_unique",
            ),
        ),
    ]
