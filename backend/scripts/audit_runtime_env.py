"""Auditoria sem vazamento de segredos: config do Compose com PostgreSQL externo.

Uso dentro do container api: python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br
Sem chamadas externas, sem banco, sem impressão de valores sensíveis.
"""
import argparse
import os
from urllib.parse import urlsplit


def inspect(env, host):
    result = []
    def check(name, ok, note):
        result.append((name, "OK" if ok else "FALHA", note))
    database = env.get("DATABASE_URL", "")
    url = urlsplit(database)
    check("DATABASE_URL", url.scheme in ("postgresql", "postgres")
          and bool(url.hostname and url.path.strip("/") and url.username and url.password),
          "PostgreSQL externo com URI completa")
    check("DJANGO_SECRET_KEY", len(env.get("DJANGO_SECRET_KEY", "")) >= 32,
          "Chave Django presente e não trivial")
    allowed = [x.strip().lower() for x in env.get("DJANGO_ALLOWED_HOSTS", "").split(",")]
    check("DJANGO_ALLOWED_HOSTS", host.lower() in allowed,
          "Host público incluído")
    origins = [x.strip().lower() for x in env.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")]
    check("DJANGO_CSRF_TRUSTED_ORIGINS", f"https://{host.lower()}" in origins,
          "Origem HTTPS incluída")
    check("DJANGO_DEBUG", env.get("DJANGO_DEBUG", "").lower() in ("0", "false"),
          "Debug desativado")
    check("DJANGO_SECURE_SSL_REDIRECT", env.get("DJANGO_SECURE_SSL_REDIRECT") == "1",
          "Redirecionamento HTTPS habilitado")
    for name in ("REDIS_URL", "CELERY_BROKER_URL"):
        parsed = urlsplit(env.get(name, ""))
        check(name, parsed.scheme in ("redis", "rediss") and bool(parsed.hostname),
              "Redis interno configurado")
    oauth = [
        "NUVEMSHOP_CLIENT_ID", "NUVEMSHOP_CLIENT_SECRET",
        "NUVEMSHOP_TOKEN_KEYS", "NUVEMSHOP_OAUTH_CALLBACK_URL",
        "NUVEMSHOP_API_USER_AGENT",
    ]
    defined = [x for x in oauth if env.get(x, "").strip()]
    if not defined:
        result.append(("NUVEMSHOP_OAUTH", "DESLIGADO", "Nenhuma credencial OAuth configurada"))
    elif len(defined) != len(oauth):
        result.append(("NUVEMSHOP_OAUTH", "ALERTA", "Configuração parcial; manter desconectado"))
    else:
        callback = urlsplit(env["NUVEMSHOP_OAUTH_CALLBACK_URL"])
        check("NUVEMSHOP_OAUTH", callback.scheme == "https"
              and callback.hostname == host.lower()
              and callback.path == "/api/v1/oauth/nuvemshop/callback/"
              and not callback.query and not callback.fragment,
              "OAuth completo; validar chave Fernet no backend")
    signup = env.get("FIDELIZA_PUBLIC_SIGNUP_ENABLED", "0").lower().strip()
    if signup in ("1", "true", "yes", "on"):
        result.append(("FIDELIZA_PUBLIC_SIGNUP_ENABLED", "ALERTA",
                       "Inscrições públicas permitidas; revisar política LGPD e autorização"))
    elif signup in ("0", "false", "", "off", "no"):
        result.append(("FIDELIZA_PUBLIC_SIGNUP_ENABLED", "OK",
                       "Inscrições públicas desativadas por padrão"))
    else:
        result.append(("FIDELIZA_PUBLIC_SIGNUP_ENABLED", "FALHA",
                       "Use apenas 0/1, false/true ou no/yes"))
    if env.get("FIDELIZA_LEDGER_WRITES_ENABLED"):
        result.append(("LEDGER", "ALERTA", "Variável de escrita ignorada: backend mantém bloqueio"))
    return result


def main():
    parser = argparse.ArgumentParser(description="Auditar stack sem expor segredos")
    parser.add_argument("--host", required=True, help="Host público da aplicação (sem protocolo)")
    args = parser.parse_args()
    if "://" in args.host or not args.host or "/" in args.host:
        parser.error("--host deve ser somente o nome DNS")
    findings = inspect(os.environ, args.host)
    for name, status, message in findings:
        print(f"{name}: {status} — {message}")
    failed = [name for name, status, _ in findings if status == "FALHA"]
    print(f"Resultado: {len(failed)} falhas obrigatórias, "
          f"{sum(s == 'ALERTA' for _, s, _ in findings)} alerta(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
