"""Fluxos de e-mail dos lojistas, independentes dos participantes do programa."""
import base64
import hashlib
import hmac
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import MerchantEmailIdentity

CHALLENGE_LIFETIME = timedelta(minutes=30)


def normalize_email(value):
    if not isinstance(value, str):
        raise ValidationError("E-mail inválido.")
    email = value.strip().casefold()
    if not email or len(email) > 254 or any(ord(char) < 32 for char in email):
        raise ValidationError("E-mail inválido.")
    validate_email(email)
    return email


def account_for_email(email):
    """Usar identidade única; legacy só quando não houver ambiguidade."""
    identity = MerchantEmailIdentity.objects.select_related("user").filter(
        normalized_email=email
    ).first()
    if identity:
        return identity.user if identity.user.is_active else None
    users = list(get_user_model().objects.filter(
        email__iexact=email, is_active=True
    )[:2])
    if len(users) == 1:
        # Nunca usar a conta legacy se o email pertence a outra identidade.
        return users[0]
    return None


def email_feature_ready():
    url = urlsplit(settings.FIDELIZA_PUBLIC_BASE_URL)
    return bool(
        settings.FIDELIZA_EMAIL_DELIVERY_ENABLED and
        url.scheme == "https" and url.hostname and
        not url.username and not url.password and not url.query and
        not url.fragment and not url.path.strip("/")
    )


def create_token(purpose, record):
    # Não armazenar tokens em claro; o worker consegue reconstruí-los.
    key = settings.SECRET_KEY.encode("utf-8")
    subject = (record.normalized_email if purpose == "register"
               else record.email_snapshot)
    message = f"fideliza:merchant:{purpose}:v1:{record.pk.hex}:{subject}".encode("utf-8")
    signature = hmac.new(key, message, hashlib.sha256).digest()
    return record.pk.hex + "." + base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")


def parse_token(value):
    if not isinstance(value, str) or len(value) > 128:
        return None
    parts = value.split(".")
    if len(parts) != 2 or len(parts[0]) != 32 or len(parts[1]) != 43:
        return None
    try:
        import uuid
        identifier = uuid.UUID(hex=parts[0])
    except ValueError:
        return None
    return identifier


def valid_token(purpose, record, candidate):
    return bool(record and record.consumed_at is None and
                record.expires_at > timezone.now() and
                hmac.compare_digest(create_token(purpose, record), candidate))


def throttle_key(purpose, email):
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
    return f"fideliza:merchant:{purpose}:{digest}"
