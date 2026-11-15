"""Evoluir SaleRecord, preservar registros manuais e não gerar saldo."""
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0003_reward_publication"),
        ("customers", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="salerecord", name="customer_profile",
            field=models.ForeignKey(
                to="customers.customerprofile", null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="channel_sales",
            ),
        ),
        migrations.AddField(
            model_name="salerecord", name="order_status",
            field=models.CharField(max_length=12, default="pending", choices=[
                ("pending", "Pendente (informado)"),
                ("paid", "Pago (informado; não conciliado)"),
                ("cancelled", "Cancelado"),
                ("refunded", "Estornado"),
            ]),
        ),
        migrations.AddField(
            model_name="salerecord", name="reported_total_cents",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="salerecord", name="reported_contact_digest",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="salerecord", name="source_order_key",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="salerecord", name="status_changed_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name="salerecord", name="channel",
            field=models.CharField(max_length=16, choices=[
                ("counter", "Balcão"), ("nuvemshop", "Nuvemshop"),
                ("whatsapp", "WhatsApp"), ("vidalys_flow", "Vidalys Flow"),
            ]),
        ),
        migrations.AlterField(
            model_name="salerecord", name="evidence_reference",
            field=models.CharField(max_length=80, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="salerecord", name="reported_paid_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name="salerecord", name="submitted_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name="submitted_manual_sales",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="salerecord", name="sales_positive_eligible_amount",
        ),
        migrations.AddConstraint(
            model_name="salerecord",
            constraint=models.CheckConstraint(
                condition=Q(eligible_amount_cents__gte=0),
                name="sales_nonnegative_eligible_amount",
            ),
        ),
        migrations.CreateModel(
            name="SaleEventReceipt",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, serialize=False, default=uuid.uuid4, editable=False,
                )),
                ("channel", models.CharField(max_length=24)),
                ("source_event_id", models.CharField(max_length=80, blank=True, default="")),
                ("idempotency_key", models.CharField(max_length=64, unique=True)),
                ("payload_digest", models.CharField(max_length=64)),
                ("reported_status", models.CharField(max_length=12, choices=[
                    ("pending", "Pendente (informado)"),
                    ("paid", "Pago (informado; não conciliado)"),
                    ("cancelled", "Cancelado"),
                    ("refunded", "Estornado"),
                ])),
                ("reported_total_cents", models.PositiveBigIntegerField()),
                ("outcome", models.CharField(max_length=12, choices=[
                    ("applied", "Estado aplicado"),
                    ("ignored", "Notificação antiga ou inválida para avançar estado"),
                ])),
                ("occurred_at", models.DateTimeField(null=True, blank=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("sale", models.ForeignKey(
                    to="sales.salerecord", on_delete=django.db.models.deletion.PROTECT,
                    related_name="inbound_events",
                )),
                ("tenant", models.ForeignKey(
                    to="tenants.tenant", on_delete=django.db.models.deletion.PROTECT,
                )),
            ],
            options={
                "ordering": ["-received_at", "-id"],
                "indexes": [
                    models.Index(fields=["sale", "received_at"], name="sales_inbox_sale_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="saleeventreceipt",
            constraint=models.UniqueConstraint(
                fields=["tenant", "channel", "source_event_id"],
                condition=~Q(source_event_id=""),
                name="sales_source_event_once",
            ),
        ),
    ]
