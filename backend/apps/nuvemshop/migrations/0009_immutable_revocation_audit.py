"""PR26: revocation confirmation is a permanent append-only receipt in PG."""
from django.db import migrations

TABLE = "nuvemshop_nuvemshopcouponrevocationaudit"
FUNCTION = "vidalys_coupon_revocation_append_only"

def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"""
            CREATE FUNCTION {FUNCTION}() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Vidalys coupon revocation append-only: %', TG_OP
                    USING ERRCODE = '23514';
            END; $$;
        """)
        cursor.execute(f"""
            CREATE TRIGGER {TABLE}_immutable BEFORE UPDATE OR DELETE ON {TABLE}
            FOR EACH ROW EXECUTE FUNCTION {FUNCTION}();
        """)

def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"DROP TRIGGER IF EXISTS {TABLE}_immutable ON {TABLE}")
        cursor.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}()")

class Migration(migrations.Migration):
    dependencies = [("nuvemshop", "0008_coupon_revocation_proof")]
    operations = [migrations.RunPython(install, reverse_code=uninstall)]
