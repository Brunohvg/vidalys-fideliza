"""Recompensas e campanhas de pontos somente em rascunho, sem efeitos externos."""
import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DiscountRewardDraft",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("title", models.CharField(max_length=100)),
                ("points_cost", models.PositiveIntegerField()),
                ("discount_cents", models.PositiveIntegerField()),
                ("min_order_cents", models.PositiveIntegerField(default=0)),
                ("max_redemptions", models.PositiveIntegerField(default=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant",on_delete=django.db.models.deletion.PROTECT,related_name="discount_reward_drafts")),
                ("updated_by", models.ForeignKey(to=settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.PROTECT,related_name="discount_reward_drafts")),
            ],
            options={"ordering":["-created_at","-id"]},
        ),
        migrations.CreateModel(
            name="PointCampaignDraft",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("goal", models.CharField(max_length=24, choices=[
                    ("second_purchase","Segunda compra"),
                    ("reactivation","Recuperar clientes"),
                    ("recurrence","Estimular recorrência"),
                ])),
                ("bonus_points", models.PositiveIntegerField()),
                ("max_customers", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant",on_delete=django.db.models.deletion.PROTECT,related_name="point_campaign_drafts")),
                ("updated_by", models.ForeignKey(to=settings.AUTH_USER_MODEL,on_delete=django.db.models.deletion.PROTECT,related_name="point_campaign_drafts")),
            ],
            options={"ordering":["-created_at","-id"]},
        ),
        migrations.AddConstraint(model_name="discountrewarddraft",
            constraint=models.CheckConstraint(condition=Q(points_cost__gt=0),
                name="reward_draft_points_positive")),
        migrations.AddConstraint(model_name="discountrewarddraft",
            constraint=models.CheckConstraint(condition=Q(discount_cents__gt=0),
                name="reward_draft_discount_positive")),
        migrations.AddConstraint(model_name="pointcampaigndraft",
            constraint=models.CheckConstraint(condition=Q(bonus_points__gt=0),
                name="point_campaign_bonus_positive")),
        migrations.AddConstraint(model_name="pointcampaigndraft",
            constraint=models.CheckConstraint(condition=Q(max_customers__gt=0),
                name="point_campaign_max_customers_positive")),
    ]
