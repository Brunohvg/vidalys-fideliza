"""Exercise real Compose precedence with Coolify's shared env_file injection.

Uses synthetic values only; never reads or prints deployment credentials.
Requires Docker Compose, but does not start containers or contact a daemon.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("api", "worker", "frontend", "redis")
# Isolamento de TODAS as variáveis conhecidas da aplicação.
# Mantido em sincronia com o Compose externo e com settings.py.
ALLOW = {
    **{key: {"api", "worker"} for key in (
        "DATABASE_URL", "DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS", "DJANGO_DEBUG",
        "DJANGO_SECURE_SSL_REDIRECT", "REDIS_URL", "CELERY_BROKER_URL",
        "FIDELIZA_EMAIL_DELIVERY_ENABLED", "FIDELIZA_PUBLIC_BASE_URL",
    )},
    **{key: {"api"} for key in (
        "NUVEMSHOP_CLIENT_ID", "NUVEMSHOP_CLIENT_SECRET", "NUVEMSHOP_TOKEN_KEYS",
        "NUVEMSHOP_OAUTH_CALLBACK_URL", "NUVEMSHOP_API_USER_AGENT",
        "FIDELIZA_PUBLIC_SIGNUP_ENABLED",
        "FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED",
        "FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED",
        "FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED",
        "FIDELIZA_PARTICIPANT_APPROVAL_ENABLED",
        "FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED",
    )},
    **{key: {"worker"} for key in (
        "EMAIL_BACKEND", "EMAIL_HOST", "EMAIL_PORT", "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD", "EMAIL_USE_TLS", "EMAIL_USE_SSL",
        "DEFAULT_FROM_EMAIL", "SERVER_EMAIL",
    )},
    **{key: set() for key in (
        "FIDELIZA_DATABASE_URL", "FIDELIZA_DJANGO_SECRET_KEY", "FIDELIZA_DB_PASSWORD",
        "SERVICE_PASSWORD_64_DJANGO", "POSTGRES_PASSWORD", "POSTGRES_USER",
        "POSTGRES_DB", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
        "FIDELIZA_HOMOLOG_LOGIN_PASSWORD", "FIDELIZA_TEST_ADMIN_PASSWORD",
        "FIDELIZA_STAGING_HOST", "FRONTEND_PORT", "FIDELIZA_LEDGER_WRITES_ENABLED",
        "FIDELIZA_SMOKE_HOMOLOG", "FIDELIZA_CI_ISOLATED",
    )},
}
# A stack força estas definições; nunca herdar valores inseguros do arquivo .env.
FIXED = {
    "DJANGO_DEBUG": "0",
    "DJANGO_SECURE_SSL_REDIRECT": "1",
    "REDIS_URL": "redis://redis:6379/0",
    "CELERY_BROKER_URL": "redis://redis:6379/1",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-command", nargs="+", default=["docker", "compose"])
    args = parser.parse_args()
    synthetic = {key: "synthetic-isolation-" + key.lower() for key in ALLOW}
    synthetic.update({
        "DATABASE_URL": "postgresql://synthetic:synthetic@database.invalid:5432/synthetic",
        "DJANGO_ALLOWED_HOSTS": "staging.invalid",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://staging.invalid",
    })
    with tempfile.TemporaryDirectory(prefix="fideliza-env-audit-") as directory:
        env_file = Path(directory) / "synthetic.env"
        env_file.write_text("".join(f"{k}={v}\n" for k, v in synthetic.items()))
        override = Path(directory) / "coolify-injection.json"
        override.write_text(json.dumps({
            "services": {name: {"env_file": [str(env_file)]} for name in SERVICES}
        }))
        # Explicit synthetic env also prevents an inherited CI secret from winning
        # interpolation precedence. Compose output stays captured, never logged.
        result = subprocess.run([
            *args.compose_command, "--project-directory", str(ROOT),
            "--env-file", str(env_file),
            "-f", str(ROOT / "compose.yaml"),
            "-f", str(override), "config", "--format", "json",
        ], env={**os.environ, **synthetic}, capture_output=True, text=True)
        if result.returncode:
            raise SystemExit("Compose configuration audit failed; no values logged.")
        services = json.loads(result.stdout)["services"]
        failures = []
        for name in SERVICES:
            values = services[name].get("environment", {})
            for key, allowed in ALLOW.items():
                expected = (FIXED.get(key, synthetic[key]) if name in allowed else "")
                if name == "worker":
                    derived = {
                        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
                        "EMAIL_PORT": "587",
                        "EMAIL_USE_TLS": "1",
                        "EMAIL_USE_SSL": "0",
                        "SERVER_EMAIL": synthetic["DEFAULT_FROM_EMAIL"],
                    }
                    expected = derived.get(key, expected)
                if values.get(key, "") != expected:
                    failures.append(f"{name}: {key}")
            if services[name].get("ports"):
                failures.append(f"{name}: public host ports")
        if failures:
            raise SystemExit("Unexpected credential scope: " + ", ".join(failures))
    print("COOLIFY_SHARED_ENV_FILE_ISOLATION_OK: API, worker, frontend, Redis")


if __name__ == "__main__":
    main()
