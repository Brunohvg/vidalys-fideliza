"""Participação interna independente de uma conta externa Nuvemshop."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("participants", "0006_member_access_challenge")]
    operations = [
        migrations.AlterField(
            model_name="programparticipant", name="external_customer_id",
            field=models.CharField(max_length=64, blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="enrollmentsubmission", name="status",
            field=models.CharField(max_length=32, default="pending_verification",
                choices=[
                    ("pending_verification", "Aguardando verificação"),
                    ("email_verified", "E-mail confirmado"),
                    ("linked", "Vínculo com a loja aprovado"),
                    ("member", "Participante confirmado sem vínculo externo"),
                    ("withdrawn", "Solicitação retirada"),
                ]),
        ),
        migrations.AddField(
            model_name="enrollmentsubmission", name="participant",
            field=models.OneToOneField(
                to="participants.programparticipant",
                on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name="local_enrollment",
            ),
        ),
    ]
