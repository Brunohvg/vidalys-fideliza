"""Tenant sem canal por padrão; sanear só cadastros pessoais sem OAuth."""
from django.db import migrations, models


def reset_unconnected_self_signup_tenants(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Membership = apps.get_model("tenants", "TenantMembership")
    Identity = apps.get_model("core", "MerchantEmailIdentity")
    Installation = apps.get_model("nuvemshop", "NuvemshopInstallation")

    owners = Membership.objects.filter(
        role="owner",
        user_id__in=Identity.objects.values_list("user_id", flat=True),
    ).values_list("tenant_id", flat=True)
    installed = Installation.objects.values_list("tenant_id", flat=True)

    # Migração idempotente, restrita a lojas criadas por cadastro próprio,
    # sem ID externo e sem instalação OAuth. Não altera integrações reais.
    Tenant.objects.filter(
        pk__in=owners,
        platform="nuvemshop",
        external_store_id__isnull=True,
    ).exclude(pk__in=installed).update(platform="independent")


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0002_tenant_branding"),
        ("core", "0002_merchant_email_claim"),
        ("nuvemshop", "0006_order_webhook_optional_launch_ts"),
    ]
    operations = [
        migrations.AlterField(
            model_name="tenant", name="platform",
            field=models.CharField(max_length=32, default="independent"),
        ),
        migrations.RunPython(
            reset_unconnected_self_signup_tenants,
            migrations.RunPython.noop,
        ),
    ]
