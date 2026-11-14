"""Auditoria sem vazamento de segredos: config do Compose com PostgreSQL externo.

Uso dentro do container api: python scripts/audit_runtime_env.py --host fideliza-homolog.optarys.com.br
Sem chamadas externas, sem banco, sem impressão de valores sensíveis.
"""
import argparse
import os
from urllib.parse import urlsplit
from cryptography.fernet import Fernet


def inspect(env, host):
    result = []
    def check(name, ok, note):
        result.append((name, "OK" if ok else "FALHA", note))
    database = env.get("DATABASE_URL", "")
    url = urlsplit(database)
    check("DATABASE_URL", url.scheme in ("postgresql", "postgres")
          and bool(url.hostname and url.path.strip("/") and url.username and url.password),
          "PostgreSQL externo com URI completa")
    if database and env.get("DB_HOST", "").strip():
        result.append(("DATABASE_CONFIGURATION_DUPLICATED", "ALERTA",
                       "DATABASE_URL tem precedência; remova DB_HOST legado do recurso"))
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
        result.append(("NUVEMSHOP_OAUTH", "FALHA", "Configuração parcial: não habilitar integração"))
    else:
        callback = urlsplit(env["NUVEMSHOP_OAUTH_CALLBACK_URL"])
        client_id = env["NUVEMSHOP_CLIENT_ID"]
        user_agent = env["NUVEMSHOP_API_USER_AGENT"]
        keys = env["NUVEMSHOP_TOKEN_KEYS"].split(",")
        key_valid = bool(keys)
        for key in keys:
            try:
                if not key.strip():
                    key_valid = False
                    break
                Fernet(key.strip().encode("ascii"))
            except (ValueError, TypeError, UnicodeError):
                key_valid = False
                break
        check("NUVEMSHOP_OAUTH",
              client_id.isascii() and client_id.isdecimal()
              and int(client_id) > 0
              and bool(env["NUVEMSHOP_CLIENT_SECRET"].strip())
              and 4 <= len(user_agent) <= 150
              and not any(ord(char) < 32 for char in user_agent)
              and key_valid and callback.scheme == "https"
              and callback.hostname == host.lower()
              and not callback.username and not callback.password
              and callback.path == "/api/v1/oauth/nuvemshop/callback/"
              and not callback.query and not callback.fragment,
              "OAuth, callback e chave de criptografia válidos")
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
    customer_preview = env.get("FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED", "0").lower().strip()
    if customer_preview in ("1", "true", "yes", "on"):
        result.append(("FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED", "ALERTA",
                       "Leitura opcional de clientes: confirmar scope read_customers e reautorização"))
    elif customer_preview in ("0", "false", "", "no", "off"):
        result.append(("FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED", "OK",
                       "Prévia de cliente desligada por padrão"))
    else:
        result.append(("FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED", "FALHA",
                       "Valor de habilitação inválido"))
    orders = env.get("FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED", "0").lower().strip()
    if orders in ("1", "true", "yes", "on"):
        result.append(("FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED", "ALERTA",
                       "Prévia restrita read_orders, sem concessão financeira"))
    elif orders in ("0", "false", "", "no", "off"):
        result.append(("FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED", "OK",
                       "Consulta de pedidos desligada"))
    else:
        result.append(("FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED", "FALHA",
                       "Valor inválido"))
    webhooks = env.get("FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED", "0").strip().lower()
    if webhooks in ("1", "true", "yes", "on"):
        result.append(("FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED", "ALERTA",
                       "Inbox assinada habilitada; confirmar app, read_orders e webhooks registrados"))
    elif webhooks in ("0", "false", "", "off", "no"):
        result.append(("FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED", "OK",
                       "Recepção de pedidos desligada no piloto"))
    else:
        result.append(("FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED", "FALHA",
                       "Valor inválido"))
    active = ("1", "true", "yes", "on")
    inactive = ("0", "false", "", "no", "off")
    oauth_ok = any(name == "NUVEMSHOP_OAUTH" and status == "OK"
                   for name, status, _ in result)
    if any(flag in active for flag in (customer_preview, orders, webhooks)):
        if not oauth_ok:
            result.append(("NUVEMSHOP_FLAG_WITHOUT_VALID_OAUTH", "FALHA",
                           "Integração ativa exige OAuth completo e validado"))
    mail = env.get("FIDELIZA_EMAIL_DELIVERY_ENABLED", "0").strip().lower()
    if mail in active:
        url = urlsplit(env.get("FIDELIZA_PUBLIC_BASE_URL", ""))
        check("FIDELIZA_EMAIL_DELIVERY_ENABLED",
              url.scheme == "https" and url.hostname == host.lower()
              and not url.username and not url.password and not url.query
              and not url.fragment and not url.path.strip("/"),
              "Email exige HTTPS canônico; SMTP deve ser conferido no worker")
    elif mail in inactive:
        result.append(("FIDELIZA_EMAIL_DELIVERY_ENABLED", "OK",
                       "Envio transacional desativado no piloto"))
    else:
        result.append(("FIDELIZA_EMAIL_DELIVERY_ENABLED", "FALHA",
                       "Flag de email inválida"))
    merchant_signup = env.get("FIDELIZA_MERCHANT_SIGNUP_ENABLED", "0").strip().lower()
    if merchant_signup in active:
        result.append(("FIDELIZA_MERCHANT_SIGNUP_ENABLED", "ALERTA",
                       "Cadastro de lojistas habilitado; exigir SMTP validado e política de dados"))
        if mail not in active:
            result.append(("MERCHANT_SIGNUP_WITHOUT_EMAIL", "FALHA",
                           "Cadastro de lojistas exige confirmação por e-mail"))
    elif merchant_signup in inactive:
        result.append(("FIDELIZA_MERCHANT_SIGNUP_ENABLED", "OK",
                       "Cadastro de lojistas fechado até homologação SMTP"))
    else:
        result.append(("FIDELIZA_MERCHANT_SIGNUP_ENABLED", "FALHA",
                       "Valor inválido"))
    if signup in active and mail not in active:
        result.append(("PUBLIC_SIGNUP_WITHOUT_EMAIL", "FALHA",
                       "Cadastro público exige confirmação por email habilitada"))
    # O SMTP é exclusivamente do worker. Nomes e estados, jamais valores.
    smtp_api_leaks = sorted(name for name in (
        "EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT",
        "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD",
        "EMAIL_USE_TLS", "EMAIL_USE_SSL",
        "DEFAULT_FROM_EMAIL", "SERVER_EMAIL",
    ) if env.get(name, "").strip())
    if smtp_api_leaks:
        result.append(("SMTP_API_ISOLATION", "FALHA",
                       "Configuração SMTP chegou à API: " + ", ".join(smtp_api_leaks)))
    else:
        result.append(("SMTP_API_ISOLATION", "OK", "SMTP restrito ao worker"))
    legacy = sorted(name for name in (
        "FIDELIZA_DATABASE_URL", "FIDELIZA_DJANGO_SECRET_KEY",
        "FIDELIZA_DB_PASSWORD", "SERVICE_PASSWORD_64_DJANGO",
        "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
        "POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD",
        "FIDELIZA_STAGING_HOST", "FRONTEND_PORT",
    ) if env.get(name, "").strip())
    if legacy:
        result.append(("LEGACY_ENV", "ALERTA",
                       "Variáveis legadas não exigidas na API: " + ", ".join(legacy)))
    unrecognized_oauth = sorted(name for name, value in env.items()
                                if name.startswith("NUVEMSHOP_")
                                and name not in oauth and str(value).strip())
    if unrecognized_oauth:
        result.append(("NUVEMSHOP_UNKNOWN_ENV", "ALERTA",
                       "Configuração Nuvemshop não reconhecida: "
                       + ", ".join(unrecognized_oauth)))
    approval = env.get("FIDELIZA_PARTICIPANT_APPROVAL_ENABLED", "0").lower().strip()
    if approval in ("1", "true", "yes", "on"):
        result.append(("FIDELIZA_PARTICIPANT_APPROVAL_ENABLED", "ALERTA",
                       "Aprovação habilitada; validar email, consentimento e OAuth por loja"))
        if customer_preview not in ("1", "true", "yes", "on"):
            result.append(("FIDELIZA_PARTICIPANT_APPROVAL_DEPENDENCY", "FALHA",
                           "Aprovação requer a prévia de cliente habilitada"))
    elif approval in ("0", "false", "", "no", "off"):
        result.append(("FIDELIZA_PARTICIPANT_APPROVAL_ENABLED", "OK",
                       "Aprovação de participantes desativada por padrão"))
    else:
        result.append(("FIDELIZA_PARTICIPANT_APPROVAL_ENABLED", "FALHA",
                       "Valor de habilitação inválido"))
    automatic = env.get("FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED","0").strip().lower()
    enabled_values=("1","true","yes","on")
    disabled_values=("0","false","","no","off")
    if automatic in enabled_values:
        result.append(("FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED","ALERTA",
                       "Vínculo automático em piloto; validar e-mail, consentimento, OAuth e LGPD"))
        if customer_preview not in enabled_values:
            result.append(("FIDELIZA_AUTO_CUSTOMER_LINK_DEPENDENCY","FALHA",
                           "Vínculo automático exige leitura de clientes habilitada"))
        if env.get("FIDELIZA_EMAIL_DELIVERY_ENABLED","0").strip().lower() not in enabled_values:
            result.append(("FIDELIZA_AUTO_EMAIL_DEPENDENCY","FALHA",
                           "Vínculo automático requer fluxo de confirmação de e-mail ativo"))
    elif automatic in disabled_values:
        result.append(("FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED","OK",
                       "Vínculo automático desativado até piloto autorizado"))
    else:
        result.append(("FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED","FALHA",
                       "Valor inválido"))
    # Uma env financeira "ligada" é insegura e enganosa: os motores reais
    # continuam hardcoded OFF em settings.py. Falhar em vez de ignorar.
    points = env.get("FIDELIZA_POINTS_WRITES_ENABLED", "").lower().strip()
    if points in ("1", "true", "yes", "on"):
        result.append(("FIDELIZA_POINTS_WRITES_ENABLED", "FALHA",
                       "Não configure ativação de pontos no .env; pagamentos e resgates não homologados"))
    elif points not in ("0", "false", "", "no", "off"):
        result.append(("FIDELIZA_POINTS_WRITES_ENABLED", "FALHA",
                       "Valor inválido; remova a variável financeira do .env"))
    else:
        result.append(("FIDELIZA_POINTS_WRITES_ENABLED", "OK",
                       "Crédito de pontos permanece bloqueado em código"))
    ledger = env.get("FIDELIZA_LEDGER_WRITES_ENABLED", "").lower().strip()
    if ledger in ("1", "true", "yes", "on"):
        result.append(("FIDELIZA_LEDGER_WRITES_ENABLED", "FALHA",
                       "Não configurar flag de saldo: lançamento bloqueado em código"))
    elif ledger not in ("0", "false", "", "no", "off"):
        result.append(("FIDELIZA_LEDGER_WRITES_ENABLED", "FALHA",
                       "Valor inválido; remova a variável financeira herdada"))
    else:
        result.append(("FIDELIZA_LEDGER_WRITES_ENABLED", "OK",
                       "Crédito financeiro bloqueado em código"))
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
