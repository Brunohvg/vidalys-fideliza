import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0003_registration_admin_labels")]

    operations = [
        migrations.CreateModel(
            name="EmailDispatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(max_length=10, choices=[
                    ("register", "Confirmação de lojista"), ("reset", "Redefinição de senha"),
                    ("verify", "Confirmação de participante"), ("withdraw", "Retirada de participante"),
                ])),
                ("reference_id", models.UUIDField()),
                ("state", models.CharField(max_length=20, default="queued", choices=[
                    ("queued", "Aguardando publicação"), ("sending", "Enviando ao SMTP"),
                    ("retry", "Retentativa programada"), ("accepted", "Aceito pelo SMTP"),
                    ("publish_failed", "Falha no Redis"), ("failed", "Falha no SMTP"),
                    ("skipped", "Não enviado"),
                ])),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(null=True, blank=True)),
                ("started_at", models.DateTimeField(null=True, blank=True)),
                ("finished_at", models.DateTimeField(null=True, blank=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("failure_type", models.CharField(max_length=60, blank=True, default="")),
            ],
            options={
                "ordering": ("-created_at",),
                "verbose_name": "Disparo de e-mail",
                "verbose_name_plural": "Disparos de e-mail",
            },
        ),
        migrations.AddIndex(model_name="emaildispatch",
                            index=models.Index(fields=["state", "created_at"], name="core_mail_dispatch_idx")),
    ]
