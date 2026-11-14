#!/usr/bin/env bash
# PR22: operador em rede PRIVADA da homologação; nunca para produção.
# Dependências: pg_dump, pg_restore, psql, sha256sum, flock, uv, git.
set -Eeuo pipefail
set +x
umask 077
die() { printf 'BLOQUEADO: %s\n' "$1" >&2; exit 1; }
require() { [[ -n "${!1:-}" ]] || die "Informe $1"; }
[[ "${FIDELIZA_ENVIRONMENT:-}" == "homolog" ]] || die "Ambiente diferente de homolog"
[[ "${FIDELIZA_MAINTENANCE_CONFIRMED:-}" == "YES" ]] || die "Confirme manutenção/sem escrita concorrente"
[[ "${FIDELIZA_APPROVE_MIGRATE:-}" == "YES_HOMOLOG_ONLY" ]] || die "Aprovação explícita ausente"
for key in DATABASE_URL FIDELIZA_EXPECTED_DATABASE FIDELIZA_RESTORE_VERIFY_DATABASE_URL FIDELIZA_APPROVED_SHA FIDELIZA_BACKUP_DIR DJANGO_SECRET_KEY; do require "$key"; done
[[ "$DATABASE_URL" == postgres://* || "$DATABASE_URL" == postgresql://* ]] || die "Origem não PostgreSQL"
[[ "$FIDELIZA_RESTORE_VERIFY_DATABASE_URL" == postgres://* || "$FIDELIZA_RESTORE_VERIFY_DATABASE_URL" == postgresql://* ]] || die "Restore não PostgreSQL"
[[ "$DATABASE_URL" != "$FIDELIZA_RESTORE_VERIFY_DATABASE_URL" ]] || die "Origem igual ao destino restore"
for binary in git pg_dump pg_restore psql sha256sum flock uv; do
  command -v "$binary" >/dev/null 2>&1 || die "Dependência ausente: $binary"
done
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ACTUAL_SHA="$(git rev-parse HEAD)" || die "Checkout Git indisponível"
[[ "$ACTUAL_SHA" == "$FIDELIZA_APPROVED_SHA" ]] || die "SHA divergente do autorizado"
[[ "$FIDELIZA_BACKUP_DIR" == /* && -d "$FIDELIZA_BACKUP_DIR" ]] || die "Diretório de backup absoluto precisa existir"
[[ ! -L "$FIDELIZA_BACKUP_DIR" ]] || die "Backup não pode usar symlink"
DIR="$(cd "$FIDELIZA_BACKUP_DIR" && pwd -P)"
[[ "$DIR" != "$ROOT" && "$DIR" != "$ROOT/"* ]] || die "Backup fora do repositório"
chmod 700 "$DIR"
exec 9>"$DIR/.migration-lock"
flock -n 9 || die "Outra migração/backup está em execução"

LIVE_NAME="$(psql "$DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 -c 'SELECT current_database()')" || die "Banco origem indisponível"
SCRATCH_NAME="$(psql "$FIDELIZA_RESTORE_VERIFY_DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 -c 'SELECT current_database()')" || die "Banco scratch indisponível"
[[ "$LIVE_NAME" == "$FIDELIZA_EXPECTED_DATABASE" ]] || die "Nome do banco origem divergente"
[[ "$SCRATCH_NAME" != "$LIVE_NAME" && "$SCRATCH_NAME" == *_restorecheck ]] || die "Destino restore precisa ser OUTRA base com sufixo _restorecheck"
SCRATCH_COUNT="$(psql "$FIDELIZA_RESTORE_VERIFY_DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")" || die "Falhou inspecionar scratch"
[[ "$SCRATCH_COUNT" == "0" ]] || die "Banco de restore não está vazio"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SHORT_SHA="$(printf '%s' "$ACTUAL_SHA" | cut -c1-12)"
BACKUP="$(mktemp "$DIR/fideliza-homolog-$STAMP-$SHORT_SHA-XXXXXX.dump")"
printf 'Backup iniciando; commit=%s\n' "$SHORT_SHA"
if ! pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-acl --lock-wait-timeout=10000 --file="$BACKUP"; then
  rm -f -- "$BACKUP"
  die "pg_dump falhou; nenhuma migração foi realizada"
fi
[[ -s "$BACKUP" ]] || die "Arquivo dump vazio"
pg_restore --list "$BACKUP" > "$BACKUP.manifest" || die "Manifest do backup inválido"
sha256sum "$BACKUP" > "$BACKUP.sha256"
(cd "$DIR" && sha256sum --check --status "$(basename "$BACKUP").sha256") || die "Checksum falhou"
# Restore REAL, mas somente na base scratch pré-criada, privada e vazia.
if ! pg_restore --exit-on-error --no-owner --no-acl --dbname="$FIDELIZA_RESTORE_VERIFY_DATABASE_URL" "$BACKUP" > "$BACKUP.restore.log" 2>&1; then
  die "Restore de conferência falhou. Logs protegidos; nenhuma migração"
fi
declare -A BEFORE_COUNTS
for table in django_migrations tenants_tenant participants_programparticipant sales_salerecord points_pointentry wallets_cashbackentry; do
  found="$(psql "$DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 -c "SELECT to_regclass('public.$table') IS NOT NULL")" || die "Falha na conferência de tabelas"
  if [[ "$found" == t ]]; then
    live_count="$(psql "$DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM public.$table")"
    scratch_count="$(psql "$FIDELIZA_RESTORE_VERIFY_DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM public.$table")"
    [[ "$live_count" == "$scratch_count" ]] || die "Restore divergente: $table"
    BEFORE_COUNTS["$table"]="$live_count"
    printf 'Restore OK: %s (%s linhas)\n' "$table" "$live_count"
  fi
done
printf 'BACKUP_VERIFIED=%s\n' "$BACKUP"
printf 'BACKUP_SHA256=%s\n' "$(cut -d ' ' -f 1 "$BACKUP.sha256")"
cd "$ROOT/backend"
uv run --locked python manage.py check || die "Django check pré-migração falhou"
uv run --locked python manage.py migrate --plan > "$BACKUP.migration-plan" || die "Plano de migração falhou"
[[ -s "$BACKUP.migration-plan" ]] || die "Plano de migração ausente"
printf 'Aplicando migrações somente após restore conferido…\n'
if ! uv run --locked python manage.py migrate --noinput > "$BACKUP.migration.log" 2>&1; then
  die "Migração falhou; impedir deploy. Restore somente com aprovação, banco isolado e sem novas escritas"
fi
uv run --locked python manage.py migrate --check || die "Migração incompleta"
uv run --locked python manage.py check || die "Django check pós-migração falhou"
# As migrações PR18–PR22 não devem inserir/remover dados comerciais legados.
for table in tenants_tenant participants_programparticipant sales_salerecord points_pointentry wallets_cashbackentry; do
  if [[ -v BEFORE_COUNTS["$table"] ]]; then
    current_count="$(psql "$DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM public.$table")"
    [[ "$current_count" == "${BEFORE_COUNTS[$table]}" ]] ||
      die "Alteração inesperada no número de registros: $table; bloquear deploy e investigar"
  fi
done
invalid_fk="$(psql "$DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated")"
[[ "$invalid_fk" == "0" ]] || die "Constraint FK não validada"
printf 'MIGRATION_COMPLETED sha=%s backup=%s\n' "$ACTUAL_SHA" "$BACKUP"
printf 'Guarde dump, checksum, manifest e logs em armazenamento privado. Exclua a base scratch somente após autorização.\n'
