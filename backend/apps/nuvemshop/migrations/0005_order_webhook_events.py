"""Recepção idempotente de avisos de pedido, sem dados do comprador."""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("nuvemshop", "0004_privacy_sanitization_evidence")]

    operations = [
        migrations.CreateModel(
            name="OrderWebhookEvent",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("store_id", models.CharField(max_length=64)),
                ("order_id", models.CharField(max_length=64)),
                ("topic", models.CharField(max_length=24, choices=[
                    ("order/paid", "Pagamento reportado"),
                    ("order/updated", "Pedido alterado"),
                ])),
                ("event_launch_ts", models.BigIntegerField()),
                ("dedupe_key", models.CharField(max_length=64, unique=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(
                    to="tenants.tenant",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="order_webhook_events",
                )),
            ],
            options={"ordering": ["-received_at"]},
        ),
        migrations.AddIndex(
            model_name="orderwebhookevent",
            index=models.Index(
                fields=["tenant", "received_at"],
                name="nuv_order_evt_tenant_idx",
            ),
        ),
    ]
