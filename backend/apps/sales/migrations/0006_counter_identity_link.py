"""Auditoria explícita de associação tardia sem reescrever eventos de ingestão."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0005_reward_redemption_terms"),
        ("customers", "0002_optional_birthday_proof"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="SaleManualLinkAudit",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False)),
                ("linked_at", models.DateTimeField(auto_now_add=True)),
                ("sale", models.OneToOneField(to="sales.salerecord",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="manual_identity_link")),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("participant", models.ForeignKey(to="participants.programparticipant",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("profile", models.ForeignKey(to="customers.customerprofile",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("linked_by", models.ForeignKey(to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
    ]
