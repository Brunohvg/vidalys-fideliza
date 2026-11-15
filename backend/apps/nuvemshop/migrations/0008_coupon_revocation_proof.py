"""PR26: serial revocation audit and safe coupon state transitions."""
import uuid
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("nuvemshop", "0007_pilot_coupons_and_rechecks"),
        ("tenants", "0004_loyalty_live_optin"),
    ]
    operations = [
        migrations.AlterField(
            model_name="nuvemshopcouponintent", name="state",
            field=models.CharField(max_length=24, default="prepared", choices=[
                ("prepared","Preparado"),("uncertain","Resultado HTTP desconhecido"),
                ("issued","Criado no provedor"),
                ("applied_pending_proof","Aplicado, captura não comprovada"),
                ("settled","Baixa financeira validada"),
                ("revoking","Revogação externa em progresso"),
                ("revoked","Revogação externa confirmada"),
            ]),
        ),
        migrations.CreateModel(
            name="NuvemshopCouponRevocationAudit",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                     editable=False, serialize=False)),
                ("reason", models.CharField(max_length=24, choices=[
                    ("expired","Voucher expirou"),
                    ("cancelled_unpaid","Pedido cancelado sem prova de captura"),
                ])),
                ("remote_id",models.CharField(max_length=64)),
                ("confirmed_at",models.DateTimeField(auto_now_add=True)),
                ("intent",models.OneToOneField(to="nuvemshop.nuvemshopcouponintent",
                    related_name="revocation_proof", on_delete=django.db.models.deletion.PROTECT)),
                ("tenant",models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.PROTECT)),
            ]
        ),
    ]
