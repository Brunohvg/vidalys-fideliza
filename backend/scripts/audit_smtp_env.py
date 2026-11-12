"""Diagnóstico SMTP2GO sem rede, sem revelar segredos, executar no container worker.

python scripts/audit_smtp_env.py --host fideliza-homolog.optarys.com.br
Não envia e-mails. Retorna erro quando --require-enabled e falta configuração.
"""
import argparse
import os
from email.utils import parseaddr
from urllib.parse import urlsplit


def assess(env, public_host):
    checks = []
    def add(name, good, detail):
        checks.append((name, "OK" if good else "FALHA", detail))

    enabled = env.get("FIDELIZA_EMAIL_DELIVERY_ENABLED", "0").lower() in ("1","true","yes","on")
    checks.append(("FIDELIZA_EMAIL_DELIVERY_ENABLED", "OK" if enabled else "DESLIGADO",
                   "Gate de envio transacional (não confirma envios reais)"))
    add("EMAIL_BACKEND", env.get("EMAIL_BACKEND") ==
        "django.core.mail.backends.smtp.EmailBackend",
        "Usar somente backend SMTP em homologação real")
    add("EMAIL_HOST", bool(env.get("EMAIL_HOST", "").strip()),
        "Servidor SMTP configurado")
    add("EMAIL_PORT", env.get("EMAIL_PORT", "") in ("587", "465"),
        "Porta segura 587/TLS ou 465/SSL")
    add("EMAIL_HOST_USER", bool(env.get("EMAIL_HOST_USER", "").strip()),
        "Usuário presente, sem exibir conteúdo")
    add("EMAIL_HOST_PASSWORD", bool(env.get("EMAIL_HOST_PASSWORD", "").strip()),
        "Senha presente, sem exibir conteúdo")
    tls = env.get("EMAIL_USE_TLS","").lower() in ("1","true","yes","on")
    ssl = env.get("EMAIL_USE_SSL","").lower() in ("1","true","yes","on")
    add("EMAIL_TRANSPORT_SECURITY", (tls != ssl) and
        ((tls and env.get("EMAIL_PORT")=="587") or
         (ssl and env.get("EMAIL_PORT")=="465")),
        "TLS/587 ou SSL/465, nunca ambos e nunca sem criptografia")
    name, sender = parseaddr(env.get("DEFAULT_FROM_EMAIL", ""))
    add("DEFAULT_FROM_EMAIL", bool(sender and sender.lower()=="contato@vidalys.com.br"),
        "Remetente Vidalys autorizado, sem exibir o endereço")
    _, server_sender = parseaddr(env.get("SERVER_EMAIL", ""))
    add("SERVER_EMAIL", server_sender.lower()==sender.lower() and bool(sender),
        "Mesmo remetente do sistema")
    # O worker nunca precisa do token nem do segredo do aplicativo Nuvemshop.
    oauth_leaks = sorted(name for name, value in env.items()
                         if name.startswith("NUVEMSHOP_") and str(value).strip())
    add("NUVEMSHOP_WORKER_ISOLATION", not oauth_leaks,
        "Worker sem credenciais ou configuração OAuth da Nuvemshop")
    base=urlsplit(env.get("FIDELIZA_PUBLIC_BASE_URL", ""))
    add("FIDELIZA_PUBLIC_BASE_URL",
        base.scheme=="https" and base.hostname==public_host.lower()
        and not base.path.strip("/") and not base.username and not base.password
        and not base.query and not base.fragment,
        "Host canônico HTTPS do Fideliza")
    return checks, enabled


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--host",required=True)
    p.add_argument("--require-enabled",action="store_true")
    args=p.parse_args()
    if not args.host or "://" in args.host or "/" in args.host:
        p.error("Informe apenas o host público")
    checks,enabled=assess(os.environ,args.host)
    for name,status,detail in checks:
        print(f"{name}: {status} — {detail}")
    failed=[x for x in checks if x[1]=="FALHA"]
    if args.require_enabled and not enabled:
        print("FALHA: envio SMTP ainda está desativado")
        return 1
    print(f"Resultado: {len(failed)} falhas. Não foi feito envio real.")
    return 1 if failed else 0


if __name__=="__main__":
    raise SystemExit(main())
