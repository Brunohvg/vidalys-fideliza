#!/usr/bin/env python3
"""PR24: atestado SOMENTE LEITURA do esquema pós-migração em homolog.

MODO schema: operador de migração; MODO runtime: role da API (mínimos privilégios).
DATABASE_URL exclusivamente do secret manager; não imprime informações do banco.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


class GateFailed(RuntimeError):
    pass


def require_env(name):
    value = os.getenv(name, "")
    if not value:
        raise GateFailed(f"Falta variável obrigatória {name}")
    return value


def main():
    if os.getenv("FIDELIZA_ENVIRONMENT") != "homolog":
        raise GateFailed("Somente homologação")
    if len(sys.argv) != 2 or sys.argv[1] not in {"schema", "runtime"}:
        raise GateFailed("Uso: python scripts/homolog_post_migrate_check.py schema|runtime")
    mode = sys.argv[1]
    expected_db = require_env("FIDELIZA_EXPECTED_DATABASE")
    expected_host = require_env("FIDELIZA_EXPECTED_PG_HOST")
    require_env("DATABASE_URL")

    import django
    django.setup()
    from django.conf import settings
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder

    if connection.vendor != "postgresql":
        raise GateFailed("O banco precisa ser PostgreSQL")
    if connection.settings_dict["HOST"] != expected_host:
        raise GateFailed("Host do PostgreSQL não corresponde ao esperado")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), current_user")
        name, role = cursor.fetchone()
        if name != expected_db:
            raise GateFailed("Banco atual diverge do aprovado")
        cursor.execute("SELECT COUNT(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated")
        if cursor.fetchone()[0]:
            raise GateFailed("Existe foreign key não validada")

    migrations = set(MigrationRecorder(connection).applied_migrations())
    required = {
        ("customers", "0001_initial"),
        ("channels", "0001_initial"),
        ("sales", "0005_reward_redemption_terms"),
        ("sales", "0006_counter_identity_link"),
        ("sales", "0007_counter_phone_digest"),
        ("participants", "0008_participant_phone"),
        ("tenants", "0005_tenant_slug_alias"),
        ("sales", "0011_credit_notice"),
        ("participants", "0009_member_birthday"),
        ("loyalty", "0002_voucher_reward_origin"),
        ("loyalty", "0003_voucher_redemption_evidence"),
        ("points", "0002_immutable_postgres_ledger"),
        ("wallets", "0002_cashback_origin_entries"),
        ("wallets", "0003_immutable_postgres_ledger"),
        ("loyalty", "0004_financial_proofs"),
        ("loyalty", "0005_immutable_payment_proofs"),
        ("nuvemshop", "0008_coupon_revocation_proof"),
        ("nuvemshop", "0009_immutable_revocation_audit"),
    }
    missing = sorted(required - migrations)
    if missing:
        raise GateFailed("Migrações obrigatórias ausentes: " + ", ".join(
            f"{app}/{migration}" for app, migration in missing))

    tables = (
        "points_pointlot", "points_pointevent", "points_pointentry",
        "wallets_cashbackevent", "wallets_cashbackentry", "wallets_cashbackoriginentry",
        "loyalty_financialevidence", "loyalty_verifiedpaymentproof",
        "loyalty_cashclosing", "nuvemshop_nuvemshopcouponrevocationaudit",
    )
    with connection.cursor() as cursor:
        for table in tables:
            expected_trigger = table + "_immutable"
            cursor.execute("""
                SELECT t.tgenabled, t.tgtype, pg_get_userbyid(c.relowner)
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                WHERE t.tgname = %s
                  AND t.tgrelid = to_regclass(%s)
                  AND NOT t.tgisinternal
            """, [expected_trigger, "public." + table])
            rows = cursor.fetchall()
            if len(rows) != 1:
                raise GateFailed(f"Trigger append-only ausente ou duplicado: {table}")
            enabled, kind, owner = rows[0]
            # Trigger type: ROW=1, BEFORE=2, DELETE=8, UPDATE=16.
            if enabled not in ("O", "A") or kind & 27 != 27:
                raise GateFailed(f"Trigger incompleto ou desabilitado: {table}")
            if mode == "runtime":
                cursor.execute("SELECT has_table_privilege(current_user, %s, 'TRUNCATE')",
                               ["public." + table])
                if cursor.fetchone()[0]:
                    raise GateFailed(f"Role da API pode executar TRUNCATE: {table}")
                if owner == role:
                    raise GateFailed(f"Role da API é dona de tabela de ledger: {table}")

        if mode == "runtime":
            cursor.execute("""
                SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication,
                       rolbypassrls FROM pg_roles WHERE rolname=current_user
            """)
            if any(cursor.fetchone()):
                raise GateFailed("Role da API tem privilégios administrativos")

    for flag in (
        "FIDELIZA_POINTS_WRITES_ENABLED",
        "FIDELIZA_LEDGER_WRITES_ENABLED",
        "FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED",
    ):
        if getattr(settings, flag, False):
            raise GateFailed(f"Gate financeiro está ON: {flag}")
    if getattr(settings, "FIDELIZA_TRUSTED_PAYMENT_ADAPTERS", frozenset()):
        raise GateFailed("Adapter PSP confiável ativado sem homologação")
    print(f"POST_MIGRATE_GATE_OK mode={mode} triggers={len(tables)} "
          f"required_migrations={len(required)} fk_invalid=0 financial_flags=OFF")


if __name__ == "__main__":
    try:
        main()
    except GateFailed as exc:
        print("POST_MIGRATE_BLOCKED: " + str(exc), file=sys.stderr)
        sys.exit(2)
