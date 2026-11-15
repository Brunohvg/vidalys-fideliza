"""PR26: append-only corroborated PSP/cash receipts and precise cash closings."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("loyalty", "0003_voucher_redemption_evidence"),
        ("tenants", "0004_loyalty_live_optin"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="CashClosing",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                    serialize=False, editable=False)),
                ("external_receipt", models.CharField(max_length=100)),
                ("amount_cents", models.PositiveBigIntegerField()),
                ("closed_at", models.DateTimeField()),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("operator", models.ForeignKey(to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.PROTECT)),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.AddConstraint(
            model_name="cashclosing",
            constraint=models.UniqueConstraint(fields=("tenant","external_receipt"),
                name="loyalty_cash_close_receipt_unique"),
        ),
        migrations.CreateModel(
            name="VerifiedPaymentProof",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                    serialize=False, editable=False)),
                ("proof_method", models.CharField(max_length=24,choices=[
                    ("pagarme_v5_get","Pagar.me v5 reconsulta"),
                    ("cash_close","Fechamento de caixa autenticado")])),
                ("reference_digest", models.CharField(max_length=64)),
                ("captured_at", models.DateTimeField()),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("evidence", models.OneToOneField(to="loyalty.financialevidence",
                    related_name="verified_payment_proof",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("operator", models.ForeignKey(to=settings.AUTH_USER_MODEL,
                    null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
    ]
