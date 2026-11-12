"""Docker CI em GitHub Actions: um único compose.yaml e banco independente.

Container PostgreSQL efêmero ligado à rede privada de CI, sem portas.
Não toca Coolify, nunca imprime senhas, URLs de DB ou tokens.
"""
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HOST = "staging.invalid"

PROXY_CHECK = """
import http.client

conn = http.client.HTTPConnection("frontend", 8080, timeout=5)
conn.request("GET", "/api/v1/auth/session/", headers={"Host": "staging.invalid"})
r = conn.getresponse()
assert r.status == 301, r.status
assert r.getheader("Location", "").startswith("https://staging.invalid/")
r.read()
conn.request("GET", "/api/v1/auth/session/", headers={
    "Host": "staging.invalid", "X-Forwarded-Proto": "https"})
r = conn.getresponse()
assert r.status == 200, r.status
assert "Secure" in r.getheader("Set-Cookie", "")
r.read()
conn.request("POST", "/api/v1/auth/login/", body="{}", headers={
    "Host": "staging.invalid", "X-Forwarded-Proto": "https",
    "Content-Type": "application/json"})
r = conn.getresponse()
assert r.status == 403, r.status
r.read()
conn.close()
"""


def execute(args, env, *, label, stdin=None, timeout=600):
    result = subprocess.run(
        args, cwd=ROOT, env=env, input=stdin, text=True,
        capture_output=True, timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError("ETAPA_FALHOU: " + label)
    print("OK: " + label, flush=True)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["basic", "proxy", "full"], required=True)
    args = parser.parse_args()
    if os.getenv("GITHUB_ACTIONS") != "true":
        raise SystemExit("Somente GitHub Actions com recursos descartáveis")
    suffix = secrets.token_hex(4)
    project = "fideliza-ci-" + suffix
    database_container = "fideliza-ci-postgres-" + suffix
    db_network = project + "-db-external"
    proxy_network = project + "-proxy-external"
    password = secrets.token_hex(32)
    env = {
        **os.environ,
        "FIDELIZA_DB_NETWORK": db_network,
        "FIDELIZA_PROXY_NETWORK": proxy_network,
        "DJANGO_SECRET_KEY": secrets.token_hex(40),
        "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1,frontend," + HOST,
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://" + HOST,
        "DATABASE_URL": "postgresql://fideliza:" + password + "@fideliza-db:5432/fideliza",
        "FIDELIZA_PUBLIC_BASE_URL": "https://" + HOST,
    }
    for flag in (
        "FIDELIZA_PUBLIC_SIGNUP_ENABLED",
        "FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED",
        "FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED",
        "FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED",
        "FIDELIZA_PARTICIPANT_APPROVAL_ENABLED",
        "FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED",
        "FIDELIZA_EMAIL_DELIVERY_ENABLED",
    ):
        env[flag] = "0"
    for key in (
        "NUVEMSHOP_CLIENT_ID", "NUVEMSHOP_CLIENT_SECRET", "NUVEMSHOP_TOKEN_KEYS",
        "NUVEMSHOP_OAUTH_CALLBACK_URL", "NUVEMSHOP_API_USER_AGENT",
        "EMAIL_HOST_PASSWORD", "EMAIL_HOST_USER",
    ):
        env[key] = ""
    compose = ["docker", "compose", "-p", project, "-f", "compose.yaml"]
    try:
        execute(["docker", "network", "create", db_network], env,
                label="rede externa privada descartavel")
        execute(["docker", "network", "create", proxy_network], env,
                label="rede do proxy descartavel")
        execute(compose + ["config", "--quiet"], env, label="compose unico Raw valido")
        execute(compose + ["up", "-d", "--wait", "--wait-timeout", "180", "redis"],
                env, label="rede e Redis privados")
        redis_id = execute(compose + ["ps", "-q", "redis"], env,
                           label="container Redis identificado")
        network = execute(
            ["docker", "inspect", "--format",
             "{{range $name, $config := .NetworkSettings.Networks}}{{$name}}{{end}}",
             redis_id], env, label="rede efêmera identificada",
        )
        if not network.startswith(project + "_"):
            raise RuntimeError("Rede fora do projeto descartável")
        execute([
            "docker", "run", "-d", "--name", database_container,
            "--network", db_network, "--network-alias", "fideliza-db",
            "--env", "POSTGRES_USER=fideliza",
            "--env", "POSTGRES_DB=fideliza",
            "--env", "POSTGRES_PASSWORD=" + password,
            "--health-cmd", "pg_isready -U fideliza -d fideliza",
            "--health-interval", "5s", "--health-timeout", "3s",
            "--health-retries", "20", "postgres:16-alpine",
        ], env, label="PostgreSQL fora do Compose")
        for attempt in range(40):
            state = execute(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}",
                 database_container], env, label="saúde PostgreSQL",
            )
            if state == "healthy":
                break
            time.sleep(2)
        else:
            raise RuntimeError("PostgreSQL externo não ficou saudável")
        execute(compose + ["up", "-d", "--build", "--wait", "--wait-timeout", "180"],
                env, label="API, worker e frontend saudáveis")
        # Isolamento no Docker inspect (containers de verdade), nao so YAML.
        # NUNCA imprimir valores de ambiente.
        import json
        from check_coolify_env_isolation import verify_service_env
        live = {}
        for name in ("api", "worker", "frontend", "redis"):
            identifier = execute(compose + ["ps", "-q", name], env,
                                 label="identificar container " + name)
            raw = execute(["docker", "inspect", "--format",
                           "{{json .Config.Env}}", identifier], env,
                          label="inspecionar env privada " + name)
            live[name] = dict(line.split("=", 1) for line in json.loads(raw)
                              if "=" in line)
        violations = verify_service_env(live)
        if violations:
            raise RuntimeError("Segredos fora do escopo: " + ", ".join(violations))
        print("RAW_CONTAINER_ENV_ISOLATION_OK", flush=True)
        execute(compose + [
            "exec", "-T", "frontend", "wget", "-q", "-O", "/dev/null",
            "--header=Host: " + HOST, "--header=X-Forwarded-Proto: https",
            "http://127.0.0.1:8080/api/ready/",
        ], env, label="readiness via frontend")
        execute(compose + [
            "exec", "-T", "api", "python", "scripts/audit_runtime_env.py",
            "--host", HOST,
        ], env, label="auditoria de ambiente")
        if args.mode in ("proxy", "full"):
            execute(compose + ["exec", "-T", "api", "python", "-"], env,
                    stdin=PROXY_CHECK, label="HTTPS, sessão, CSRF")
        execute(compose + [
            "exec", "-T", "worker", "celery", "-A", "config",
            "inspect", "ping", "--timeout", "5",
        ], env, label="worker e broker Redis")
        if args.mode == "full":
            script = (ROOT / ".github/scripts/smoke_real_auth.py").read_text()
            execute(compose + [
                "exec", "-T", "-e", "FIDELIZA_CI_ISOLATED=1",
                "api", "python", "-",
            ], env, stdin=script, label="login/CSRF/tenant/campanhas")
        print("SINGLE_COMPOSE_SMOKE_OK: " + args.mode, flush=True)
    finally:
        subprocess.run(
            ["docker", "rm", "-fv", database_container],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        subprocess.run(
            compose + ["down", "-v", "--remove-orphans"],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        for name in (db_network, proxy_network):
            subprocess.run(["docker", "network", "rm", name],
                           cwd=ROOT, env=env, capture_output=True, text=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired):
        print("FALHA: ambiente CI da stack, verificar etapa registrada.", file=sys.stderr)
        raise SystemExit(1) from None
