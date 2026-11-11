# Fundação privada para futuras adesões verificadas. Não importa clientes.
import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("tenants", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ProgramParticipant",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("external_customer_id", models.CharField(max_length=64)),
                ("display_name", models.CharField(blank=True, default="", max_length=140)),
                ("contact_email", models.EmailField(blank=True, default="", max_length=254)),
                ("consent_at", models.DateTimeField()),
                ("consent_channel", models.CharField(choices=[("customer_portal", "Portal do participante"), ("storefront_opt_in", "Aceite na vitrine")], max_length=32)),
                ("terms_version", models.CharField(max_length=40)),
                ("status", models.CharField(choices=[("active", "Participando"), ("paused", "Pausado"), ("withdrawn", "Adesão encerrada")], default="active", max_length=16)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("last_program_activity_at", models.DateTimeField(blank=True, null=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE, related_name="program_participants")),
            ],
            options={"ordering": ["-joined_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="programparticipant",
            constraint=models.UniqueConstraint(
                fields=("tenant", "external_customer_id"), name="loyalty_tenant_customer_unique"
            ),
        ),
        migrations.AddIndex(
            model_name="programparticipant",
            index=models.Index(fields=["tenant", "status", "joined_at"], name="loyalty_tenant_member_idx"),
        ),
    ]
