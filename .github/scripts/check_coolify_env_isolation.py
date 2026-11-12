"""Validate Raw Coolify Compose (allowlist) and prove Managed injection leaks.

No Docker daemon required. All test credentials are fabricated. Never print
secrets, container env, rendered Compose, or Docker inspect values.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("api", "worker", "frontend", "redis")
SMTP = {
    "EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT", "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD", "EMAIL_USE_TLS", "EMAIL_USE_SSL",
    "DEFAULT_FROM_EMAIL", "SERVER_EMAIL",
}
OAUTH = {
    "NUVEMSHOP_CLIENT_ID", "NUVEMSHOP_CLIENT_SECRET",
    "NUVEMSHOP_TOKEN_KEYS", "NUVEMSHOP_OAUTH_CALLBACK_URL",
    "NUVEMSHOP_API_USER_AGENT",
}
DJANGO = {
    "DJANGO_SECRET_KEY", "DATABASE_URL", "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS", "DJANGO_DEBUG",
    "DJANGO_SECURE_SSL_REDIRECT", "REDIS_URL", "CELERY_BROKER_URL",
    "FIDELIZA_PUBLIC_BASE_URL", "FIDELIZA_EMAIL_DELIVERY_ENABLED",
}
API_ONLY = {
    "FIDELIZA_PUBLIC_SIGNUP_ENABLED", "FIDELIZA_MERCHANT_SIGNUP_ENABLED",
    "FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED",
    "FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED",
    "FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED",
    "FIDELIZA_PARTICIPANT_APPROVAL_ENABLED",
    "FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED",
}
LEGACY = {
    "SERVICE_PASSWORD_64_DJANGO", "FIDELIZA_DATABASE_URL",
    "FIDELIZA_DJANGO_SECRET_KEY", "FIDELIZA_DB_PASSWORD",
    "FIDELIZA_HOMOLOG_LOGIN_PASSWORD", "FIDELIZA_TEST_ADMIN_PASSWORD",
    "FIDELIZA_STAGING_HOST", "POSTGRES_PASSWORD", "POSTGRES_USER",
    "POSTGRES_DB", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER",
    "DB_PASSWORD", "FRONTEND_PORT", "FIDELIZA_LEDGER_WRITES_ENABLED",
    "FIDELIZA_SMOKE_HOMOLOG", "FIDELIZA_CI_ISOLATED",
}
ALL = SMTP | OAUTH | DJANGO | API_ONLY | LEGACY


def verify_service_env(services):
    """Return NAMES only; do not log values."""
    findings = []
    for service in SERVICES:
        env = services.get(service, {})
        if service not in services:
            findings.append(service + ":missing")
            continue
        allowed = {
            "api": DJANGO | OAUTH | API_ONLY,
            "worker": DJANGO | SMTP,
            "redis": set(),
            "frontend": set(),
        }[service]
        for key in sorted(ALL):
            if key in env and key not in allowed:
                findings.append(service + ":" + key)
        for key in (
            ("DATABASE_URL", "DJANGO_SECRET_KEY") if service in ("api", "worker")
            else ()
        ):
            if not env.get(key, "").strip():
                findings.append(service + ":missing_" + key)
        for key in ("NUVEMSHOP_CLIENT_SECRET", "NUVEMSHOP_TOKEN_KEYS"):
            if service != "api" and key in env:
                findings.append(service + ":" + key)
    return sorted(set(findings))


def render(env, *, injection=None):
    cmd = [
        "docker", "compose", "--project-directory", str(ROOT),
        "--env-file", env["FIDELIZA_SYNTH_ENV_FILE"],
        "-f", str(ROOT / "compose.yaml"),
    ]
    if injection:
        cmd.extend(["-f", injection])
    result = subprocess.run(
        cmd + ["config", "--format", "json"],
        capture_output=True, text=True,
        env={**os.environ, **env},
    )
    if result.returncode:
        raise SystemExit("Compose Raw invalid; details intentionally suppressed.")
    return json.loads(result.stdout)["services"]


def main():
    synthetic = {k: "synthetic-only-" + k.lower() for k in ALL}
    synthetic.update({
        "DATABASE_URL": "postgresql://synthetic:synthetic@database.invalid:5432/synthetic",
        "DJANGO_ALLOWED_HOSTS": "staging.invalid",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://staging.invalid",
        "FIDELIZA_DB_NETWORK": "synthetic-db-network",
        "FIDELIZA_PROXY_NETWORK": "synthetic-proxy-network",
        "DEFAULT_FROM_EMAIL": "Synthetic <synthetic@example.invalid>",
    })
    with tempfile.TemporaryDirectory(prefix="fideliza-raw-config-") as d:
        f = Path(d) / "synthetic.env"
        f.write_text("".join(f"{k}={v}\n" for k, v in synthetic.items()))
        synthetic["FIDELIZA_SYNTH_ENV_FILE"] = str(f)
        raw = render(synthetic)
        actual = {k: raw[k].get("environment", {}) for k in SERVICES}
        leaks = verify_service_env(actual)
        if leaks:
            raise SystemExit("RAW_SCOPE_FAIL: " + ", ".join(leaks))
        for name in SERVICES:
            entry = raw[name]
            if entry.get("env_file") or entry.get("ports"):
                raise SystemExit("Raw contains shared env_file or public ports: " + name)
            network_names = set(entry.get("networks", {}))
            expected = {
                "api": {"app", "database"},
                "worker": {"app", "database"},
                "frontend": {"app", "proxy"},
                "redis": {"app"},
            }[name]
            if network_names != expected:
                raise SystemExit("Invalid network scope: " + name)
        # Regressao do parser Coolify: o arquivo FONTE precisa ter labels
        # como lista de strings. Mapeamentos podem virar 0: key=value
        # na etapa de geracao, rejeitados no deploy real.
        original = (ROOT / "compose.yaml").read_text()
        frontend_source = original.split("\n  frontend:\n", 1)
        if len(frontend_source) != 2:
            raise SystemExit("Missing unique frontend source service")
        labels_source = frontend_source[1].split("\n    labels:\n", 1)
        if len(labels_source) != 2:
            raise SystemExit("Missing unique frontend labels")
        block = labels_source[1].split("\n    mem_limit:", 1)[0]
        label_lines = block.strip("\n").splitlines()
        if (len(label_lines) < 8 or
                any(not line.startswith("      - ") for line in label_lines)):
            raise SystemExit("COOLIFY_LABELS_SOURCE_FAIL: use string sequence, not key mapping")
        if any("0:" in line[:9] or "1:" in line[:9] for line in label_lines):
            raise SystemExit("COOLIFY_LABELS_NUMERIC_KEY_FAIL")
        source_label_names = [
            line.strip()[2:].strip().strip(chr(34)).split("=", 1)[0]
            for line in label_lines
        ]
        if len(source_label_names) != len(set(source_label_names)):
            raise SystemExit("COOLIFY_DUPLICATE_TRAEFIK_LABELS")
        if "traefik.enable" not in source_label_names:
            raise SystemExit("COOLIFY_TRAEFIK_DISABLED")
        if not any(name.endswith(".tls.certresolver") for name in source_label_names):
            raise SystemExit("COOLIFY_TLS_RESOLVER_MISSING")
        # Controle negativo: preserva cobertura para regressao de labels
        # com chaves numericas, exatamente o erro reportado no Coolify.
        broken = "    labels:\\n      0: traefik.enable=true\\n"
        if not any(not line.startswith("      - ")
                   for line in broken.replace("\\n", "\n").splitlines()[1:]):
            raise SystemExit("COOLIFY_LABELS_NEGATIVE_CONTROL_MISSED")
        labels = raw["frontend"].get("labels", {})
        if labels.get("traefik.enable") != "true":
            raise SystemExit("Traefik Raw route missing")
        if not any("fideliza-homolog.optarys.com.br" in str(value)
                   for value in labels.values()):
            raise SystemExit("Public domain route missing")
        # NEGATIVE CONTROL: managed Coolify adds an env_file to every service.
        # The same synthetic values MUST now leak, proving detection works.
        override = Path(d) / "managed-injection.json"
        override.write_text(json.dumps({
            "services": {name: {"env_file": [str(f)]} for name in SERVICES}
        }))
        managed = render(synthetic, injection=str(override))
        injected = {k: managed[k].get("environment", {}) for k in SERVICES}
        detected = verify_service_env(injected)
        if not any("frontend:DATABASE_URL" == x for x in detected):
            raise SystemExit("Negative control failed to detect leaked DB credentials")
        if not any("api:EMAIL_HOST_PASSWORD" == x for x in detected):
            raise SystemExit("Negative control failed to detect leaked SMTP credentials")
    print("RAW_SCOPE_OK: four services, external networks, TLS labels")
    print("MANAGED_INJECTION_DETECTED: negative control blocks leaked secrets")


if __name__ == "__main__":
    main()
