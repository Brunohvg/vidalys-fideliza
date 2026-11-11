"""Acompanhamento mínimo de solicitações LGPD, sem dados sensíveis do webhook."""
import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("nuvemshop", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="PrivacyWebhookRequest",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                     editable=False, serialize=False)),
                ("store_id", models.CharField(max_length=64)),
                ("customer_id", models.CharField(max_length=64, default="", blank=True)),
                ("request_id", models.CharField(max_length=64, default="", blank=True)),
                ("topic", models.CharField(max_length=40, choices=[
                    ("customer/redact", "Excluir dados do consumidor"),
                    ("customers/data_request", "Relatório de dados do consumidor"),
                    ("app/store_redact", "Excluir dados da loja"),
                ])),
                ("event_key", models.CharField(max_length=64, unique=True)),
                ("state", models.CharField(max_length=20, default="pending", choices=[
                    ("pending", "Aguardando tratamento"),
                    ("needs_review", "Exige revisão de privacidade"),
                    ("completed", "Concluído após verificação"),
                    ("unknown_store", "Loja não associada ao aplicativo"),
                ])),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(null=True, blank=True)),
                ("reason_code", models.CharField(max_length=40, default="", blank=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant", null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="privacy_requests")),
            ],
            options={"ordering": ["-received_at"]},
        ),
        migrations.AddIndex(
            model_name="privacywebhookrequest",
            index=models.Index(fields=["tenant", "state", "received_at"],
                               name="nuv_priv_tenant_state_idx"),
        ),
    ]
