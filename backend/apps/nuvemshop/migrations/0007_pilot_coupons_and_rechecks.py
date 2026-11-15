"""PR25: vínculo imutável lógico entre voucher e cupom Nuvemshop."""
import uuid
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("nuvemshop", "0006_order_webhook_optional_launch_ts"),
        ("loyalty", "0003_voucher_redemption_evidence"),
        ("tenants", "0004_loyalty_live_optin"),
    ]
    operations = [
        migrations.CreateModel(
            name="NuvemshopCouponIntent",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False)),
                ("store_id", models.CharField(max_length=64)),
                ("encrypted_code", models.TextField()),
                ("code_sha256", models.CharField(max_length=64, unique=True)),
                ("remote_coupon_id", models.CharField(max_length=64, blank=True, default="")),
                ("order_id", models.CharField(max_length=32, blank=True, default="")),
                ("state", models.CharField(max_length=24, default="prepared", choices=[
                    ("prepared","Preparado"),("uncertain","Resultado HTTP desconhecido"),
                    ("issued","Criado no provedor"),
                    ("applied_pending_proof","Aplicado, captura não comprovada"),
                    ("settled","Baixa financeira validada")
                ])),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("voucher", models.OneToOneField(to="loyalty.loyaltyvoucher",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="nuvemshop_coupon")),
            ],
        ),
        migrations.AddConstraint(
            model_name="nuvemshopcouponintent",
            constraint=models.UniqueConstraint(
                fields=["tenant", "order_id"], condition=~models.Q(order_id=""),
                name="nuv_pilot_one_coupon_per_order",
            ),
        ),
        migrations.CreateModel(
            name="NuvemshopOrderRecheck",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,
                    serialize=False)),
                ("status", models.CharField(max_length=24, default="pending")),
                ("summary_digest", models.CharField(max_length=64, blank=True, default="")),
                ("checked_at", models.DateTimeField(null=True, blank=True)),
                ("event", models.OneToOneField(to="nuvemshop.orderwebhookevent",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="order_recheck")),
            ],
        ),
    ]
