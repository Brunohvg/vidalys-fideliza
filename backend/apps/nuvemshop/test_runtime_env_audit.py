"""Auditoria das flags e credenciais sem vazamento de valores."""
from cryptography.fernet import Fernet
from django.test import SimpleTestCase
from scripts.audit_runtime_env import inspect

HOST = "staging.invalid"


def environment():
    return {
        "DATABASE_URL": "postgresql://u:p@private-db.invalid:5432/fideliza",
        "DJANGO_SECRET_KEY": "synthetic-test-key-at-least-32-characters",
        "DJANGO_ALLOWED_HOSTS": f"localhost,{HOST}",
        "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://{HOST}",
        "DJANGO_DEBUG": "0",
        "DJANGO_SECURE_SSL_REDIRECT": "1",
        "REDIS_URL": "redis://redis:6379/0",
        "CELERY_BROKER_URL": "redis://redis:6379/1",
    }


def statuses(env):
    return {name: status for name, status, _ in inspect(env, HOST)}


class RuntimeEnvAuditTests(SimpleTestCase):
    def test_no_oauth_and_all_flags_off_is_valid(self):
        result = statuses(environment())
        self.assertNotIn("FALHA", result.values())
        self.assertEqual(result["NUVEMSHOP_OAUTH"], "DESLIGADO")
        self.assertEqual(result["FIDELIZA_LEDGER_WRITES_ENABLED"], "OK")

    def test_partial_or_invalid_oauth_fails(self):
        base = environment()
        self.assertEqual(
            statuses({**base, "NUVEMSHOP_CLIENT_ID": "123"})["NUVEMSHOP_OAUTH"],
            "FALHA",
        )
        keys = {
            "NUVEMSHOP_CLIENT_ID": "123",
            "NUVEMSHOP_CLIENT_SECRET": "synthetic-client-secret",
            "NUVEMSHOP_OAUTH_CALLBACK_URL":
                f"https://{HOST}/api/v1/oauth/nuvemshop/callback/",
            "NUVEMSHOP_API_USER_AGENT": "Fideliza QA (qa@example.invalid)",
            "NUVEMSHOP_TOKEN_KEYS": "invalid-key",
        }
        self.assertEqual(statuses({**base, **keys})["NUVEMSHOP_OAUTH"], "FALHA")
        keys["NUVEMSHOP_TOKEN_KEYS"] = Fernet.generate_key().decode("ascii")
        self.assertEqual(statuses({**base, **keys})["NUVEMSHOP_OAUTH"], "OK")
        keys["NUVEMSHOP_OAUTH_CALLBACK_URL"] = (
            "https://attacker.invalid/api/v1/oauth/nuvemshop/callback/"
        )
        self.assertEqual(statuses({**base, **keys})["NUVEMSHOP_OAUTH"], "FALHA")

    def test_nuvemshop_flags_require_valid_oauth(self):
        for flag in (
            "FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED",
            "FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED",
            "FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED",
        ):
            with self.subTest(flag=flag):
                result = statuses({**environment(), flag: "1"})
                self.assertEqual(result["NUVEMSHOP_FLAG_WITHOUT_VALID_OAUTH"], "FALHA")

    def test_email_requires_website_url_and_signup_requires_email(self):
        self.assertEqual(
            statuses({**environment(), "FIDELIZA_EMAIL_DELIVERY_ENABLED": "1"})[
                "FIDELIZA_EMAIL_DELIVERY_ENABLED"
            ], "FALHA",
        )
        good = {
            **environment(),
            "FIDELIZA_EMAIL_DELIVERY_ENABLED": "1",
            "FIDELIZA_PUBLIC_BASE_URL": f"https://{HOST}",
        }
        self.assertEqual(
            statuses(good)["FIDELIZA_EMAIL_DELIVERY_ENABLED"], "OK"
        )
        self.assertEqual(
            statuses({**environment(), "FIDELIZA_PUBLIC_SIGNUP_ENABLED": "1"})[
                "PUBLIC_SIGNUP_WITHOUT_EMAIL"
            ], "FALHA",
        )

    def test_merchant_signup_is_separate_from_consumer_signup_and_needs_email(self):
        base = environment()
        status = statuses(base)
        self.assertEqual(status["FIDELIZA_MERCHANT_SIGNUP_ENABLED"], "OK")
        self.assertEqual(statuses({
            **base, "FIDELIZA_MERCHANT_SIGNUP_ENABLED": "1"
        })["MERCHANT_SIGNUP_WITHOUT_EMAIL"], "FALHA")
        self.assertEqual(statuses({
            **base, "FIDELIZA_MERCHANT_SIGNUP_ENABLED": "invalid"
        })["FIDELIZA_MERCHANT_SIGNUP_ENABLED"], "FALHA")
        enabled = {
            **base,
            "FIDELIZA_MERCHANT_SIGNUP_ENABLED": "1",
            "FIDELIZA_EMAIL_DELIVERY_ENABLED": "1",
            "FIDELIZA_PUBLIC_BASE_URL": f"https://{HOST}",
        }
        self.assertEqual(statuses(enabled)["FIDELIZA_MERCHANT_SIGNUP_ENABLED"], "ALERTA")
        self.assertNotIn("MERCHANT_SIGNUP_WITHOUT_EMAIL", statuses(enabled))

    def test_stale_db_host_and_financial_override_detected(self):
        self.assertEqual(
            statuses({**environment(), "DB_HOST": "old-db.invalid"})[
                "DATABASE_CONFIGURATION_DUPLICATED"
            ], "ALERTA",
        )
        self.assertEqual(
            statuses({
                **environment(), "FIDELIZA_LEDGER_WRITES_ENABLED": "1",
            })["FIDELIZA_LEDGER_WRITES_ENABLED"], "FALHA",
        )
