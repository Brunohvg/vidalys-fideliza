"""PR26: prova financeira append-only em DB, inclusive SQL direto."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

TABLES = ("loyalty_financialevidence", "loyalty_paymentproofaudit")
FUNCTION = "vidalys_immutable_payment_proof"

def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"""
        CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'Vidalys payment proof append-only: % on %', TG_OP, TG_TABLE_NAME
            USING ERRCODE = '23514';
        END; $$;
        """)
        for table in TABLES:
            cursor.execute(f"""
              CREATE TRIGGER {table}_immutable
              BEFORE UPDATE OR DELETE ON {table}
              FOR EACH ROW EXECUTE FUNCTION {FUNCTION}();
            """)

def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
        cursor.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}()")


class Migration(migrations.Migration):
    dependencies = [
        ("loyalty", "0003_voucher_redemption_evidence"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name="PaymentProofAudit", fields=[
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4,
                editable=False, serialize=False)),
            ("provider", models.CharField(max_length=48)),
            ("provider_reference", models.CharField(max_length=120, unique=True)),
            ("proof_digest", models.CharField(max_length=64)),
            ("verified_at", models.DateTimeField()),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("evidence", models.OneToOneField(
                to="loyalty.financialevidence", related_name="origin_proof",
                on_delete=django.db.models.deletion.PROTECT)),
            ("tenant", models.ForeignKey(
                to="tenants.tenant", on_delete=django.db.models.deletion.PROTECT)),
            ("sale", models.ForeignKey(
                to="sales.salerecord", on_delete=django.db.models.deletion.PROTECT)),
            ("operator", models.ForeignKey(to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name="cash_proof_operations")),
            ("reviewer", models.ForeignKey(to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name="cash_proof_reviews")),
        ]),
        migrations.RunPython(install, reverse_code=uninstall),
    ]
