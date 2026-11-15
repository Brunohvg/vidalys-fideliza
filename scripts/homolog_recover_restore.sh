#!/usr/bin/env bash
# PR24: recuperação NÃO DESTRUTIVA para NOVO banco privado e vazio.
# Jamais redireciona tráfego, remove tabelas nem restaura sobre a origem.
set -Eeuo pipefail
set +x
umask 077
die(){ printf 'RECOVERY_BLOCKED: %s\n' "$1" >&2; exit 2; }
required(){ [[ -n "${!1:-}" ]] || die "Informe $1 por secret manager"; }

[[ "${FIDELIZA_ENVIRONMENT:-}" == "homolog" ]] || die "Somente homologação"
[[ "${FIDELIZA_RECOVERY_APPROVED:-}" == "YES_NEW_EMPTY_DATABASE_ONLY" ]] ||
  die "Falta aprovação explícita de recovery em base NOVA"
[[ "${FIDELIZA_MAINTENANCE_CONFIRMED:-}" == "YES" ]] ||
  die "Não é seguro recuperar sem janela de manutenção/escritas suspensas"
for key in DATABASE_URL FIDELIZA_EXPECTED_DATABASE FIDELIZA_EXPECTED_PG_HOST \
  FIDELIZA_RECOVERY_DATABASE_URL FIDELIZA_EXPECTED_RECOVERY_PG_HOST \
  FIDELIZA_BACKUP_FILE FIDELIZA_BACKUP_EXPECTED_SHA256; do
  required "$key"
done
for binary in psql pg_restore sha256sum python3 flock mktemp; do
  command -v "$binary" >/dev/null 2>&1 || die "Dependência ausente: $binary"
done
[[ "$FIDELIZA_BACKUP_FILE" == /* && -s "$FIDELIZA_BACKUP_FILE" ]] ||
  die "Arquivo de backup absoluto e não vazio obrigatório"
[[ ! -L "$FIDELIZA_BACKUP_FILE" ]] || die "Backup não pode ser symlink"
[[ -s "$FIDELIZA_BACKUP_FILE.sha256" && -s "$FIDELIZA_BACKUP_FILE.manifest" ]] ||
  die "Checksum e manifesto do snapshot precisam existir"
[[ "$FIDELIZA_BACKUP_EXPECTED_SHA256" =~ ^[a-f0-9]{64}$ ]] ||
  die "SHA-256 aprovado inválido"

read -r ORIGINAL_HOST ORIGINAL_DB RECOVERY_HOST RECOVERY_DB < <(
  python3 - <<'PY'
import os
from urllib.parse import urlsplit
a = urlsplit(os.environ["DATABASE_URL"])
b = urlsplit(os.environ["FIDELIZA_RECOVERY_DATABASE_URL"])
print(a.hostname or "", a.path.lstrip("/"), b.hostname or "", b.path.lstrip("/"))
PY
)
[[ "$ORIGINAL_HOST" == "$FIDELIZA_EXPECTED_PG_HOST" &&
   "$ORIGINAL_DB" == "$FIDELIZA_EXPECTED_DATABASE" ]] ||
  die "Origem não corresponde à homologação autorizada"
[[ "$RECOVERY_HOST" == "$FIDELIZA_EXPECTED_RECOVERY_PG_HOST" &&
   "$RECOVERY_DB" == *_recoverycheck && "$RECOVERY_DB" != "$ORIGINAL_DB" ]] ||
  die "Destino deve ser outra base privada terminada em _recoverycheck"
[[ "$DATABASE_URL" != "$FIDELIZA_RECOVERY_DATABASE_URL" ]] ||
  die "Origem e destino não podem coincidir"

DIR="$(dirname "$FIDELIZA_BACKUP_FILE")"
exec 9>"$DIR/.homolog-recovery.lock"
flock -n 9 || die "Outra recuperação em andamento"
ACTUAL_SHA="$(sha256sum "$FIDELIZA_BACKUP_FILE" | cut -d' ' -f1)"
[[ "$ACTUAL_SHA" == "$FIDELIZA_BACKUP_EXPECTED_SHA256" ]] ||
  die "Dump diferente do SHA-256 aprovado"
sha256sum --check --status "$FIDELIZA_BACKUP_FILE.sha256" ||
  die "Falha na conferência adicional do checksum"

EMPTY="$(psql "$FIDELIZA_RECOVERY_DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 \
  -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")" ||
  die "Não foi possível conferir base nova"
[[ "$EMPTY" == "0" ]] || die "Base de recuperação já possui tabelas"
LOG="$(mktemp "$DIR/fideliza-recovery-XXXXXXXX.log")"
if ! pg_restore --single-transaction --no-owner --no-acl \
    --dbname="$FIDELIZA_RECOVERY_DATABASE_URL" "$FIDELIZA_BACKUP_FILE" >"$LOG" 2>&1; then
  die "pg_restore falhou. Não trocar DATABASE_URL; consultar log protegido"
fi
TABLE="$(psql "$FIDELIZA_RECOVERY_DATABASE_URL" -X -q -A -t \
  -v ON_ERROR_STOP=1 -c "SELECT to_regclass('public.django_migrations') IS NOT NULL")"
[[ "$TABLE" == "t" ]] || die "Base recuperada sem tabela django_migrations"
FK_INVALID="$(psql "$FIDELIZA_RECOVERY_DATABASE_URL" -X -q -A -t \
  -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated")"
[[ "$FK_INVALID" == "0" ]] || die "FK inválida no recovery"
printf 'RECOVERY_NEW_DATABASE_READY db=%s sha256=%s fk_invalid=0\n' "$RECOVERY_DB" "$ACTUAL_SHA"
printf 'NÃO foi alterada a origem. Troca de DATABASE_URL e rollback de código exigem aprovação adicional.\n'
