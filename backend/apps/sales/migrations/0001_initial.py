"""Registros de vendas e rascunho de pontos, sem lançamento financeiro."""
import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("participants", "0007_standalone_participant"),
        ("tenants", "0003_unconnected_merchant_tenants"),
    ]
    operations = [
        migrations.CreateModel(
            name="PointRuleDraft",
            fields=[
                ("tenant", models.OneToOneField(
                    to="tenants.tenant", on_delete=django.db.models.deletion.PROTECT,
                    primary_key=True, serialize=False, related_name="point_rule_draft",
                )),
                ("version", models.PositiveIntegerField(default=1)),
                ("points", models.PositiveIntegerField(default=1)),
                ("per_cents", models.PositiveIntegerField(default=100)),
                ("hold_days", models.PositiveSmallIntegerField(default=7)),
                ("validity_days", models.PositiveSmallIntegerField(default=180)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT,
                    related_name="saved_point_rules",
                )),
            ],
        ),
        migrations.CreateModel(
            name="SaleRecord",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                    serialize=False, editable=False)),
                ("channel", models.CharField(max_length=16, choices=[
                    ("counter", "Balcão"), ("nuvemshop", "Nuvemshop"),
                    ("whatsapp", "WhatsApp"),
                ])),
                ("external_reference", models.CharField(max_length=80)),
                ("eligible_amount_cents", models.PositiveBigIntegerField()),
                ("currency", models.CharField(max_length=3, default="BRL", editable=False)),
                ("reported_paid_at", models.DateTimeField()),
                ("evidence_reference", models.CharField(max_length=80)),
                ("state", models.CharField(max_length=24, default="awaiting_review",
                    choices=[
                        ("awaiting_member", "Sem participante"),
                        ("awaiting_review", "Conferência pendente"),
                        ("verified_manual", "Venda manual conferida"),
                        ("rejected", "Rejeitada"),
                    ])),
                ("review_note", models.CharField(max_length=240, blank=True, default="")),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("participant", models.ForeignKey(
                    to="participants.programparticipant",
                    on_delete=django.db.models.deletion.PROTECT,
                    null=True, blank=True, related_name="sales_records",
                )),
                ("tenant", models.ForeignKey(
                    to="tenants.tenant", on_delete=django.db.models.deletion.PROTECT,
                    related_name="sales_records",
                )),
                ("submitted_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT,
                    related_name="submitted_manual_sales",
                )),
                ("reviewed_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT,
                    null=True, blank=True, related_name="reviewed_manual_sales",
                )),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="salerecord", constraint=models.UniqueConstraint(
                fields=("tenant", "channel", "external_reference"),
                name="sales_unique_channel_document",
            ),
        ),
        migrations.AddConstraint(
            model_name="salerecord", constraint=models.CheckConstraint(
                condition=Q(eligible_amount_cents__gt=0),
                name="sales_positive_eligible_amount",
            ),
        ),
        migrations.AddIndex(
            model_name="salerecord",
            index=models.Index(fields=["tenant", "state", "created_at"],
                               name="sales_tenant_state_idx"),
        ),
    ]
