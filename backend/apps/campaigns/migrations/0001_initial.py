"""Persistência isolada de planejamento. Não executa campanhas."""
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
            name="CampaignDraft",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False, editable=False, default=uuid.uuid4)),
                ("title", models.CharField(max_length=90)),
                ("goal", models.CharField(max_length=24, choices=[
                    ("second_purchase", "Segunda compra"),
                    ("reactivation", "Reativação"),
                    ("recurrence", "Recorrência"),
                ])),
                ("cashback_rate_bps", models.PositiveSmallIntegerField()),
                ("ticket_cents", models.PositiveBigIntegerField()),
                ("projected_paid_orders", models.PositiveIntegerField()),
                ("budget_cents", models.PositiveBigIntegerField()),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name="+")),
                ("updated_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name="+")),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.CASCADE, related_name="campaign_drafts")),
            ],
            options={"ordering": ["-updated_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="campaigndraft",
            constraint=models.CheckConstraint(
                condition=Q(cashback_rate_bps__gte=1, cashback_rate_bps__lte=1000),
                name="draft_cashback_bps_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="campaigndraft",
            constraint=models.CheckConstraint(
                condition=Q(ticket_cents__gt=0, ticket_cents__lte=1_000_000_000),
                name="draft_ticket_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="campaigndraft",
            constraint=models.CheckConstraint(
                condition=Q(budget_cents__gt=0, budget_cents__lte=1_000_000_000),
                name="draft_budget_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="campaigndraft",
            constraint=models.CheckConstraint(
                condition=Q(projected_paid_orders__gte=1, projected_paid_orders__lte=50000),
                name="draft_paid_orders_range",
            ),
        ),
    ]
