"""Contrato da env verificado com valores inteiramente sintéticos."""
from scripts.audit_runtime_env import inspect
from scripts.audit_smtp_env import assess


def runtime():
    return {
        "DATABASE_URL": "postgresql://fake:fake@database.invalid:5432/fideliza",
        "DJANGO_SECRET_KEY": "synthetic-key-value-1234567890123456789",
        "DJANGO_ALLOWED_HOSTS": "staging.invalid",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://staging.invalid",
        "DJANGO_DEBUG": "0",
        "DJANGO_SECURE_SSL_REDIRECT": "1",
        "REDIS_URL": "redis://redis:6379/0",
        "CELERY_BROKER_URL": "redis://redis:6379/1",
    }


def inspect_map(env):
    return {name: state for name, state, note in inspect(env, "staging.invalid")}


def test_api_clean_env_rejects_unnecessary_smtp_and_legacies():
    clean = inspect_map(runtime())
    assert clean["DATABASE_URL"] == "OK"
    assert clean["NUVEMSHOP_OAUTH"] == "DESLIGADO"
    assert clean["SMTP_API_ISOLATION"] == "OK"
    assert "LEGACY_ENV" not in clean
    for key in ("EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL", "EMAIL_PORT",
                "EMAIL_BACKEND", "EMAIL_HOST_USER", "SERVER_EMAIL"):
        assert inspect_map({**runtime(), key: "synthetic"})["SMTP_API_ISOLATION"] == "FALHA"


def test_api_reports_legacy_and_unknown_keys_without_exposing_values():
    env = {**runtime(), "DB_HOST": "dont-leak-this-host",
           "NUVEMSHOP_UNUSED_TOKEN": "dont-leak-this-value"}
    detail = inspect(env, "staging.invalid")
    results = {name: state for name, state, _ in detail}
    assert results["LEGACY_ENV"] == "ALERTA"
    assert results["NUVEMSHOP_UNKNOWN_ENV"] == "ALERTA"
    assert "dont-leak-this-value" not in str(detail)
    assert "dont-leak-this-host" not in str(detail)


def test_worker_smtp_contract_and_nuvemshop_isolation():
    env = {
        "FIDELIZA_EMAIL_DELIVERY_ENABLED": "0",
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": "mail.smtp2go.com", "EMAIL_PORT": "587",
        "EMAIL_HOST_USER": "synthetic-user",
        "EMAIL_HOST_PASSWORD": "synthetic-password",
        "EMAIL_USE_TLS": "1", "EMAIL_USE_SSL": "0",
        "DEFAULT_FROM_EMAIL": "Vidalys <contato@vidalys.com.br>",
        "SERVER_EMAIL": "Vidalys <contato@vidalys.com.br>",
        "FIDELIZA_PUBLIC_BASE_URL": "https://staging.invalid",
    }
    checks, enabled = assess(env, "staging.invalid")
    assert not enabled
    assert all(state != "FALHA" for _, state, _ in checks)
    env["NUVEMSHOP_CLIENT_SECRET"] = "dont-leak-this-key"
    checks, _ = assess(env, "staging.invalid")
    assert any(name == "NUVEMSHOP_WORKER_ISOLATION" and state == "FALHA"
               for name, state, _ in checks)
    assert "dont-leak-this-key" not in str(checks)



def test_financial_env_flag_never_activates_ledger_or_points():
    clean = inspect_map(runtime())
    assert clean["FIDELIZA_POINTS_WRITES_ENABLED"] == "OK"
    assert clean["FIDELIZA_LEDGER_WRITES_ENABLED"] == "OK"
    for flag in ("FIDELIZA_POINTS_WRITES_ENABLED", "FIDELIZA_LEDGER_WRITES_ENABLED"):
        for truthy in ("1", "on", "TRUE", "yes"):
            result = inspect_map({**runtime(), flag: truthy})
            assert result[flag] == "FALHA"
        assert inspect_map({**runtime(), flag: "not-a-boolean"})[flag] == "FALHA"
        assert inspect_map({**runtime(), flag: "0"})[flag] == "OK"


def test_independent_membership_is_visible_and_not_silently_enabled():
    clean = inspect_map(runtime())
    assert clean["FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED"] == "OK"
    assert inspect_map({**runtime(),
        "FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED": "1",
    })["FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED"] == "ALERTA"
    assert inspect_map({**runtime(),
        "FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED": "wrong",
    })["FIDELIZA_STANDALONE_MEMBERSHIP_ENABLED"] == "FALHA"


def test_merchant_signup_cannot_be_opened_without_email_gate():
    assert inspect_map({**runtime(),
        "FIDELIZA_MERCHANT_SIGNUP_ENABLED": "1",
    })["MERCHANT_SIGNUP_WITHOUT_EMAIL"] == "FALHA"
    states = inspect_map({**runtime(),
        "FIDELIZA_MERCHANT_SIGNUP_ENABLED": "1",
        "FIDELIZA_EMAIL_DELIVERY_ENABLED": "1",
        "FIDELIZA_PUBLIC_BASE_URL": "https://staging.invalid",
    })
    assert states["FIDELIZA_MERCHANT_SIGNUP_ENABLED"] == "ALERTA"
    assert "MERCHANT_SIGNUP_WITHOUT_EMAIL" not in states
    assert states["FIDELIZA_EMAIL_DELIVERY_ENABLED"] == "OK"
