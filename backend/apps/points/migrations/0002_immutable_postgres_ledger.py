"""Proteção nativa do histórico de pontos (PostgreSQL only)."""
from django.db import migrations

TABLES = ("points_pointlot", "points_pointevent", "points_pointentry")
FUNCTION = "vidalys_points_immutable_ledger"

def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"""
            CREATE FUNCTION {FUNCTION}() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Vidalys ledger append-only: % on %', TG_OP, TG_TABLE_NAME
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
    dependencies = [("points", "0001_initial")]
    operations = [migrations.RunPython(install, reverse_code=uninstall)]
