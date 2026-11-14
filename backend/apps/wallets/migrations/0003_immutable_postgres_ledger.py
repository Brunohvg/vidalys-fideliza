"""PostgreSQL: o histórico do ledger é append-only inclusive via SQL direto.

SQLite dos testes locais não tem trigger PG; testes específicos de imutabilidade
usam PostgreSQL externo descartável. Não bloqueia INSERT nem movimentos de compensação.
"""
from django.db import migrations

TABLES = (
    "wallets_cashbackevent",
    "wallets_cashbackentry",
    "wallets_cashbackoriginentry",
)
FUNCTION = "vidalys_wallets_immutable_ledger"

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
        for name in TABLES:
            cursor.execute(f"""
                CREATE TRIGGER {name}_immutable
                BEFORE UPDATE OR DELETE ON {name}
                FOR EACH ROW EXECUTE FUNCTION {FUNCTION}();
            """)

def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for name in TABLES:
            cursor.execute(f"DROP TRIGGER IF EXISTS {name}_immutable ON {name}")
        cursor.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}()")

class Migration(migrations.Migration):
    dependencies = [("wallets", "0002_cashback_origin_entries")]
    operations = [migrations.RunPython(install, reverse_code=uninstall)]
