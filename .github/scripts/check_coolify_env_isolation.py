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
ALLOW = {
    "DATABASE_URL": {"api", "worker"},
    "DJANGO_SECRET_KEY": {"api", "worker"},
    **{key: {"api"} for key in (
        "NUVEMSHOP_CLIENT_ID", "NUVEMSHOP_CLIENT_SECRET", "NUVEMSHOP_TOKEN_KEYS",
        "NUVEMSHOP_OAUTH_CALLBACK_URL", "NUVEMSHOP_API_USER_AGENT",
    )},
    "EMAIL_HOST_USER": {"worker"},
    "EMAIL_HOST_PASSWORD": {"worker"},
    "FIDELIZA_PUBLIC_SIGNUP_ENABLED": {"api"},
    "FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED": {"api"},
    "FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED": {"api"},
    "FIDELIZA_PARTICIPANT_APPROVAL_ENABLED": {"api"},
    "FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED": {"api"},
    "FIDELIZA_EMAIL_DELIVERY_ENABLED": {"api","worker"},
    "FIDELIZA_PUBLIC_BASE_URL": {"api","worker"},
    **{key: set() for key in (
        "FIDELIZA_DATABASE_URL", "FIDELIZA_DJANGO_SECRET_KEY", "FIDELIZA_DB_PASSWORD",
        "SERVICE_PASSWORD_64_DJANGO", "POSTGRES_PASSWORD", "DB_PASSWORD",
        "FIDELIZA_HOMOLOG_LOGIN_PASSWORD", "FIDELIZA_TEST_ADMIN_PASSWORD",
    )},
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
            "-f", str(ROOT / "compose.coolify.external-db.yaml"),
            "-f", str(override), "config", "--format", "json",
        ], env={**os.environ, **synthetic}, capture_output=True, text=True)
        if result.returncode:
            raise SystemExit("Compose configuration audit failed; no values logged.")
        services = json.loads(result.stdout)["services"]
        failures = []
        for name in SERVICES:
            values = services[name].get("environment", {})
            for key, allowed in ALLOW.items():
                expected = synthetic[key] if name in allowed else ""
                if values.get(key, "") != expected:
                    failures.append(f"{name}: {key}")
            if services[name].get("ports"):
                failures.append(f"{name}: public host ports")
        if failures:
            raise SystemExit("Unexpected credential scope: " + ", ".join(failures))
    print("COOLIFY_SHARED_ENV_FILE_ISOLATION_OK: API, worker, frontend, Redis")


if __name__ == "__main__":
    main()
