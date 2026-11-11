"""Comprovação de e-mail e retirada da pré-adesão, sem promover participantes."""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("participants", "0003_privacy_notice")]
    operations = [
        migrations.AddField(
            model_name="enrollmentsubmission",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="enrollmentsubmission",
            name="withdrawn_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="enrollmentsubmission",
            name="status",
            field=models.CharField(max_length=32, default="pending_verification", choices=[
                ("pending_verification", "Aguardando verificação"),
                ("email_verified", "E-mail confirmado"),
                ("withdrawn", "Solicitação retirada"),
            ]),
        ),
        migrations.CreateModel(
            name="EnrollmentEmailChallenge",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                    primary_key=True, serialize=False)),
                ("purpose", models.CharField(max_length=12, choices=[
                    ("verify", "Confirmar e-mail"), ("withdraw", "Retirar solicitação"),
                ])),
                ("token_digest", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("submission", models.ForeignKey(to="participants.enrollmentsubmission",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="email_challenges")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="enrollmentemailchallenge",
            index=models.Index(fields=["submission", "purpose", "created_at"],
                               name="fideliza_email_chal_idx"),
        ),
    ]
