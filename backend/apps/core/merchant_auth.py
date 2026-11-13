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
from django.db.models import Q
from django.utils import timezone

from .models import MerchantEmailClaim, MerchantEmailIdentity, MerchantRegistration

CHALLENGE_LIFETIME = timedelta(minutes=30)


def normalize_email(value):
    if not isinstance(value, str):
        raise ValidationError("E-mail inválido.")
    email = value.strip().casefold()
    if not email or len(email) > 254 or any(ord(char) < 32 for char in email):
        raise ValidationError("E-mail inválido.")
    validate_email(email)
    return email


def canonical_email(email):
    """Somente Gmail público: '+' e pontos são aliases da mesma caixa.

    Outros provedores podem tratar esses caracteres como endereços distintos:
    não normalizar além do casefold sem contrato do provedor.
    """
    local, domain = email.rsplit("@", 1)
    if domain in ("gmail.com", "googlemail.com"):
        return local.split("+", 1)[0].replace(".", "") + "@gmail.com"
    return email


def _gmail_matches(queryset, key, field):
    """Compatibilidade com contas anteriores à tabela de reivindicações."""
    for row in queryset.filter(
        Q(**{field + "__iendswith": "@gmail.com"}) |
        Q(**{field + "__iendswith": "@googlemail.com"})
    ).values_list(field, flat=True):
        if row and canonical_email(row.strip().casefold()) == key:
            return True
    return False


def email_claimed(email):
    """Falha fechada: qualquer conta existente bloqueia novo cadastro.

    Não confundir 'login ambíguo' com 'email disponível'. Contas técnicas
    ou legadas, ativas ou não, também reservam seus endereços.
    """
    key = canonical_email(email)
    if MerchantEmailClaim.objects.filter(canonical_email=key).exists():
        return True
    if MerchantEmailIdentity.objects.filter(normalized_email=email).exists():
        return True
    User = get_user_model()
    if User.objects.filter(email__iexact=email).exists():
        return True
    if key.endswith("@gmail.com"):
        return (
            _gmail_matches(User.objects.all(), key, "email") or
            _gmail_matches(MerchantEmailIdentity.objects.all(), key, "normalized_email")
        )
    return False


def blocked_registration_for_email(email):
    """Bloqueio administrativo da inscrição vale também para aliases Gmail."""
    key = canonical_email(email)
    blocked = MerchantRegistration.objects.filter(blocked_at__isnull=False)
    if blocked.filter(normalized_email=email).exists():
        return True
    if key.endswith("@gmail.com"):
        return _gmail_matches(blocked, key, "normalized_email")
    return False


def pending_email_claimed(email):
    key = canonical_email(email)
    pending = MerchantRegistration.objects.filter(
        consumed_at__isnull=True, cancelled_at__isnull=True,
        blocked_at__isnull=True, expires_at__gt=timezone.now())
    if pending.filter(normalized_email=email).exists():
        return True
    if key.endswith("@gmail.com"):
        return _gmail_matches(pending, key, "normalized_email")
    return False


def pending_registration_for_email(email):
    """Retorna a mesma solicitação pendente para aliases da caixa Gmail.

    O destinatário do reenvio permanece o endereço originalmente confirmado
    por quem iniciou o cadastro. Em outros provedores, exija igualdade.
    """
    pending = MerchantRegistration.objects.filter(
        consumed_at__isnull=True, cancelled_at__isnull=True,
        blocked_at__isnull=True, expires_at__gt=timezone.now(),
    )
    direct = pending.filter(normalized_email=email).first()
    if direct:
        return direct
    key = canonical_email(email)
    if key.endswith("@gmail.com"):
        for row in pending.filter(
            Q(normalized_email__iendswith="@gmail.com")
            | Q(normalized_email__iendswith="@googlemail.com")
        ).order_by("-requested_at"):
            if canonical_email(row.normalized_email) == key:
                return row
    return None


def account_for_email(email):
    """Usar identidade única; legacy só quando não houver ambiguidade."""
    claim = MerchantEmailClaim.objects.select_related("user").filter(
        canonical_email=canonical_email(email)
    ).first()
    if claim:
        return claim.user if claim.user.is_active else None
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
                getattr(record, "cancelled_at", None) is None and
                getattr(record, "blocked_at", None) is None and
                record.expires_at > timezone.now() and
                hmac.compare_digest(create_token(purpose, record), candidate))


def throttle_key(purpose, email):
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
    return f"fideliza:merchant:{purpose}:{digest}"
