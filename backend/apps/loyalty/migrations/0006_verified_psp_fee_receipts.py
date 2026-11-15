"""PR30: immutable PSP fees from authenticated, complete payables."""
import uuid
from django.db import migrations, models
import django.db.models.deletion


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute("""
            CREATE TRIGGER loyalty_verifiedpspfeereceipt_immutable
            BEFORE UPDATE OR DELETE ON loyalty_verifiedpspfeereceipt
            FOR EACH ROW EXECUTE FUNCTION vidalys_payment_proof_append_only();
        """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute("""
            DROP TRIGGER IF EXISTS loyalty_verifiedpspfeereceipt_immutable
            ON loyalty_verifiedpspfeereceipt
        """)


class Migration(migrations.Migration):
    dependencies = [("loyalty","0005_immutable_payment_proofs")]
    operations = [
        migrations.CreateModel(
            name="VerifiedPspFeeReceipt",
            fields=[
                ("id",models.UUIDField(primary_key=True,default=uuid.uuid4,
                                      editable=False,serialize=False)),
                ("charge_digest",models.CharField(max_length=64,unique=True)),
                ("payables_digest",models.CharField(max_length=64)),
                ("gross_cents",models.PositiveBigIntegerField()),
                ("fee_cents",models.PositiveBigIntegerField()),
                ("net_cents",models.PositiveBigIntegerField()),
                ("payable_count",models.PositiveSmallIntegerField()),
                ("verified_at",models.DateTimeField(auto_now_add=True)),
                ("tenant",models.ForeignKey(to="tenants.tenant",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("proof",models.OneToOneField(to="loyalty.verifiedpaymentproof",
                    related_name="fee_receipt",
                    on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.RunPython(install,reverse_code=uninstall),
    ]
