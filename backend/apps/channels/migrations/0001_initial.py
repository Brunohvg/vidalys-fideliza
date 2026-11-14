import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0003_unconnected_merchant_tenants"),
    ]
    operations = [
        migrations.CreateModel(
            name="ChannelCredential",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, serialize=False, default=uuid.uuid4, editable=False,
                )),
                ("channel", models.CharField(
                    max_length=24, choices=[("vidalys_flow", "Vidalys Flow")],
                )),
                ("label", models.CharField(max_length=80)),
                ("key_hash", models.CharField(max_length=256)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(null=True, blank=True)),
                ("revoked_at", models.DateTimeField(null=True, blank=True)),
                ("tenant", models.ForeignKey(
                    to="tenants.tenant", on_delete=django.db.models.deletion.PROTECT,
                    related_name="channel_credentials",
                )),
            ],
            options={"indexes": [
                models.Index(fields=["tenant", "channel"], name="channel_key_tenant_idx"),
            ]},
        ),
    ]
