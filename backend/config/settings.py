"""Configuração por ambiente sem credenciais no repositório."""
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.getenv(name, "1" if default else "0").lower() in ("1", "yes", "true", "on")


DEBUG = env_bool("DJANGO_DEBUG")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "local-development-only-not-for-deployment"
    else:
        raise RuntimeError("Configure DJANGO_SECRET_KEY")

ALLOWED_HOSTS = [v.strip() for v in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if v.strip()]
CSRF_TRUSTED_ORIGINS = [v.strip() for v in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if v.strip()]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "apps.core.apps.CoreConfig", "apps.tenants.apps.TenantsConfig",
    "apps.margin.apps.MarginConfig",
    "apps.costs.apps.CostsConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.nuvemshop.apps.NuvemshopConfig",
    "apps.participants.apps.ParticipantsConfig",
    "apps.campaigns.apps.CampaignsConfig",
    "apps.wallets.apps.WalletsConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [],
    "APP_DIRS": True, "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]}}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

url = os.getenv("DATABASE_URL", "")
if url:
    parsed = urlparse(url)
    if parsed.scheme == "sqlite":
        name = ":memory:" if parsed.path in ("/:memory:", ":memory:") else parsed.path
        DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": name}}
    elif parsed.scheme in ("postgres", "postgresql"):
        DATABASES = {"default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"), "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "", "PORT": parsed.port or 5432,
            "CONN_MAX_AGE": 60,
        }}
    else:
        raise RuntimeError("DATABASE_URL precisa ser sqlite ou postgresql")
elif os.getenv("DB_HOST"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "vidalys_fideliza"),
        "USER": os.getenv("DB_USER", "vidalys"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.environ["DB_HOST"], "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }}
elif DEBUG:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "local.sqlite3"}}
else:
    raise RuntimeError("Configure DB_HOST ou DATABASE_URL (PostgreSQL na homologação)")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "UTC"
USE_TZ = True
USE_I18N = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
# Somente use com proxy que substitua X-Forwarded-Proto e sem acesso externo direto à API.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT")
SESSION_COOKIE_SECURE = not DEBUG and SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = not DEBUG and SECURE_SSL_REDIRECT
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_IGNORE_RESULT = True
# Worker único na homologação: não reservar quatro tarefas adiantadas.
# Ajuda a manter a fila responsiva se houver processamento mais demorado.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1


# Limitação de tentativas de login compartilhada entre workers em homologação/produção.
# O Redis do Compose não expõe portas externas.
REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
# Em desenvolvimento sem Redis, Django usa cache local em memória.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
SESSION_SAVE_EVERY_REQUEST = False

# Bloqueado: concessões e resgates dependem de autorização e eventos verificados.
FIDELIZA_LEDGER_WRITES_ENABLED = False

# Registro público desativado até a homologação do fluxo de dados pessoais.
FIDELIZA_PUBLIC_SIGNUP_ENABLED = env_bool("FIDELIZA_PUBLIC_SIGNUP_ENABLED", False)

# Leitura de clientes somente após reautorização da loja e liberação explícita.
FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED = env_bool(
    "FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED", False
)

# Consulta de pedidos só para auditoria, nunca para conceder saldo.
FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED = env_bool(
    "FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED", False
)

# Recepção de eventos autenticados somente no piloto, sem crédito de saldo.
FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED = env_bool(
    "FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED", False
)

# Manual approval of verified participants; NO cashback/ledger activation.
FIDELIZA_PARTICIPANT_APPROVAL_ENABLED = env_bool(
    "FIDELIZA_PARTICIPANT_APPROVAL_ENABLED", False
)

# Após consentimento e confirmação do e-mail, vínculo automático só se a
# conta exata for encontrada na própria loja Nuvemshop. Não concede cashback.
# OFF até validação do OAuth read_customers, envio SMTP e LGPD no piloto.
FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED = env_bool(
    "FIDELIZA_AUTO_CUSTOMER_LINK_ENABLED", False
)


# Contrato SMTP compatível com Mérito/QueroLink, isolado por aplicação no Coolify.
# Desabilitado até que remetente Vidalys e credenciais sejam validados.
FIDELIZA_EMAIL_DELIVERY_ENABLED = env_bool("FIDELIZA_EMAIL_DELIVERY_ENABLED", False)
FIDELIZA_PUBLIC_BASE_URL = os.getenv("FIDELIZA_PUBLIC_BASE_URL", "").strip()
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
# Containers sem SMTP recebem EMAIL_PORT vazio por isolamento do Coolify.
EMAIL_PORT = int(os.getenv("EMAIL_PORT") or "587")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "").strip()
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL).strip()

# Cadastro publico de LOJISTAS; independente da adesao dos clientes dos programas.
# OFF ate SMTP do worker validado, politica de privacidade e homologacao do fluxo.
FIDELIZA_MERCHANT_SIGNUP_ENABLED = env_bool("FIDELIZA_MERCHANT_SIGNUP_ENABLED", False)
