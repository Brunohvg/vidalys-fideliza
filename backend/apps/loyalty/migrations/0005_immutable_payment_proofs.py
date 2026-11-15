"""PR26: evidence, PSP proof and cash closings are immutable in PostgreSQL."""
from django.db import migrations

TABLES = (
    "loyalty_financialevidence",
    "loyalty_verifiedpaymentproof",
    "loyalty_cashclosing",
)
FUNCTION = "vidalys_payment_proof_append_only"


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"""
            CREATE FUNCTION {FUNCTION}() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Vidalys payment proof append-only: %', TG_OP
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
    dependencies = [("loyalty", "0004_financial_proofs")]
    operations = [migrations.RunPython(install, reverse_code=uninstall)]
