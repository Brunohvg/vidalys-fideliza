"""Registro auditável de remoção de participante pela loja. Só acrescenta."""
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("participants", "0010_merchant_assisted_consent"),
        ("tenants", "0005_tenant_slug_alias"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="ParticipantRemoval",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reason", models.CharField(blank=True, default="", max_length=240)),
                ("reversed_units", models.PositiveIntegerField(default=0)),
                ("coupons_cancelled", models.PositiveIntegerField(default=0)),
                ("data_result", models.CharField(default="erased", max_length=16)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+",
                                            to=settings.AUTH_USER_MODEL)),
                ("participant", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="removal",
                                                     to="participants.programparticipant")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="participant_removals",
                                             to="tenants.tenant")),
            ],
        ),
    ]
