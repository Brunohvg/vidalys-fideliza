"""Cadastro e recuperação de acesso do LOJISTA; cliente final usa outro fluxo."""
import hashlib
import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from apps.tenants.models import Tenant, TenantMembership
from .merchant_auth import (
    CHALLENGE_LIFETIME, account_for_email, canonical_email, email_claimed,
    pending_email_claimed, email_feature_ready, normalize_email,
    parse_token, throttle_key, valid_token,
)
from .models import MerchantEmailClaim, MerchantEmailIdentity, MerchantRegistration, MerchantPasswordReset
from .delivery_tracking import enqueue_email

logger = logging.getLogger(__name__)
GENERIC_ACCEPTED = {"detail": "Se o e-mail puder receber esta solicitação, enviaremos as instruções."}


def _body(request):
    if not request.content_type.startswith("application/json") or len(request.body) > 4096:
        return None
    try:
        data = json.loads(request.body)
        return data if isinstance(data, dict) else None
    except (ValueError, UnicodeError):
        return None


def _email(request):
    body = _body(request)
    try:
        return body, normalize_email(body.get("email")) if body else None
    except ValidationError:
        return body, None


def _queue(purpose, record_id):
    from .tasks import send_merchant_auth_email
    return enqueue_email(purpose, record_id, send_merchant_auth_email,
                         purpose, str(record_id))

def _enabled():
    return settings.FIDELIZA_MERCHANT_SIGNUP_ENABLED and email_feature_ready()


@never_cache
@sensitive_post_parameters("password")
@csrf_protect
@require_POST
def register(request):
    if not _enabled():
        return JsonResponse({"detail": "Cadastro temporariamente indisponível. Tente mais tarde."}, status=503)
    body, email = _email(request)
    if not body or not email:
        return JsonResponse({"detail": "Informe um e-mail válido."}, status=400)
    first = body.get("name")
    store = body.get("store_name")
    password = body.get("password")
    if (not isinstance(first, str) or not 2 <= len(first.strip()) <= 100 or
        not isinstance(store, str) or not 2 <= len(store.strip()) <= 140 or
        not isinstance(password, str) or not 12 <= len(password) <= 4096):
        return JsonResponse({"detail": "Preencha nome, loja e uma senha com ao menos 12 caracteres."}, status=400)
    try:
        validate_password(password)
    except ValidationError:
        return JsonResponse({"detail": "Escolha uma senha mais forte, com 12 ou mais caracteres."}, status=400)
    if not cache.add(throttle_key("register", canonical_email(email)), 1, timeout=60):
        return JsonResponse(GENERIC_ACCEPTED, status=202)
    if email_claimed(email) or pending_email_claimed(email):
        return JsonResponse(GENERIC_ACCEPTED, status=202)
    now = timezone.now()
    try:
        with transaction.atomic():
            MerchantRegistration.objects.filter(
                normalized_email=email, expires_at__lte=now
            ).delete()
            if not pending_email_claimed(email):
                pending = MerchantRegistration.objects.create(
                    normalized_email=email, first_name=first.strip(),
                    store_name=store.strip(), password_hash=make_password(password),
                    expires_at=now + CHALLENGE_LIFETIME,
                )
                _queue("register", pending.pk)
    except IntegrityError:
        pass  # Uma solicitação concorrente já reservou o endereço.
    return JsonResponse(GENERIC_ACCEPTED, status=202)


@never_cache
@csrf_protect
@require_POST
def resend_registration(request):
    if not _enabled():
        return JsonResponse({"detail": "Confirmação por e-mail temporariamente indisponível."}, status=503)
    _, email = _email(request)
    if not email:
        return JsonResponse({"detail": "Informe um e-mail válido."}, status=400)
    if cache.add(throttle_key("resend", canonical_email(email)), 1, timeout=60):
        pending = MerchantRegistration.objects.filter(
            normalized_email=email, consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).first()
        if pending and not email_claimed(email):
            _queue("register", pending.pk)
    return JsonResponse(GENERIC_ACCEPTED, status=202)


@never_cache
@csrf_protect
@require_POST
def confirm_registration(request):
    data = _body(request)
    token = data.get("token") if data else None
    identifier = parse_token(token)
    if not identifier:
        return JsonResponse({"detail": "Link inválido ou expirado."}, status=400)
    try:
        with transaction.atomic():
            pending = MerchantRegistration.objects.select_for_update().get(
                pk=identifier
            )
            if not valid_token("register", pending, token):
                return JsonResponse({"detail": "Link inválido ou expirado."}, status=400)
            if email_claimed(pending.normalized_email):
                return JsonResponse({"detail": "Este cadastro não pode ser concluído."}, status=409)
            User = get_user_model()
            # Username interno não é o identificador público; o email é único na identidade.
            user = User(username="merch_" + uuid.uuid4().hex,
                        email=pending.normalized_email, first_name=pending.first_name,
                        is_active=True, is_staff=False, is_superuser=False)
            user.password = pending.password_hash
            user.save()
            MerchantEmailClaim.objects.create(
                user=user, canonical_email=canonical_email(pending.normalized_email),
            )
            MerchantEmailIdentity.objects.create(
                user=user, normalized_email=pending.normalized_email,
                verified_at=timezone.now(),
            )
            tenant = Tenant.objects.create(
                name=pending.store_name,
                slug=(slugify(pending.store_name)[:35] or "loja") + "-" +
                     uuid.uuid4().hex[:12],
                platform="independent", status=Tenant.Status.ACTIVE,
                external_store_id=None,
            )
            TenantMembership.objects.create(
                user=user, tenant=tenant, role=TenantMembership.Role.OWNER
            )
            pending.consumed_at = timezone.now()
            pending.password_hash = "!"
            pending.save(update_fields=["consumed_at", "password_hash"])
        # Confirmado: sessão real e loja criada, sem depender de Nuvemshop.
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return JsonResponse({"authenticated": True, "detail": "Conta confirmada."})
    except (MerchantRegistration.DoesNotExist, IntegrityError):
        return JsonResponse({"detail": "Link inválido ou expirado."}, status=400)


@never_cache
@csrf_protect
@require_POST
def request_password_reset(request):
    if not email_feature_ready():
        return JsonResponse({"detail": "Recuperação por e-mail temporariamente indisponível."}, status=503)
    _, email = _email(request)
    if not email:
        return JsonResponse({"detail": "Informe um e-mail válido."}, status=400)
    if not cache.add(throttle_key("reset", canonical_email(email)), 1, timeout=60):
        return JsonResponse(GENERIC_ACCEPTED, status=202)
    user = account_for_email(email)
    if user and user.has_usable_password():
        # Enviar sempre ao endereço confirmado, mesmo se pedido via alias.
        identity = MerchantEmailIdentity.objects.filter(user=user).first()
        destination = identity.normalized_email if identity else user.email.strip().casefold()
        with transaction.atomic():
            MerchantPasswordReset.objects.filter(user=user,
                consumed_at__isnull=True).update(consumed_at=timezone.now())
            reset = MerchantPasswordReset.objects.create(
                user=user, email_snapshot=destination,
                expires_at=timezone.now() + CHALLENGE_LIFETIME
            )
            _queue("reset", reset.pk)
    return JsonResponse(GENERIC_ACCEPTED, status=202)


@never_cache
@sensitive_post_parameters("password")
@csrf_protect
@require_POST
def confirm_password_reset(request):
    data = _body(request)
    token = data.get("token") if data else None
    password = data.get("password") if data else None
    identifier = parse_token(token)
    if not identifier or not isinstance(password, str) or len(password) > 4096:
        return JsonResponse({"detail": "Link inválido ou dados incompletos."}, status=400)
    if len(password) < 12:
        return JsonResponse({"detail": "A senha deve ter ao menos 12 caracteres."}, status=400)
    try:
        validate_password(password)
    except ValidationError:
        return JsonResponse({"detail": "Escolha uma senha mais forte."}, status=400)
    try:
        with transaction.atomic():
            reset = MerchantPasswordReset.objects.select_for_update().select_related(
                "user"
            ).get(pk=identifier)
            if not valid_token("reset", reset, token) or not reset.user.is_active:
                return JsonResponse({"detail": "Link inválido ou expirado."}, status=400)
            identity = MerchantEmailIdentity.objects.filter(user=reset.user).first()
            current_email = (identity.normalized_email if identity else
                             reset.user.email.casefold().strip())
            if current_email != reset.email_snapshot:
                return JsonResponse({"detail": "Link inválido ou expirado."}, status=400)
            reset.user.set_password(password)
            reset.user.save(update_fields=["password"])
            reset.consumed_at = timezone.now()
            reset.save(update_fields=["consumed_at"])
        return JsonResponse({"detail": "Senha atualizada. Entre com seu e-mail."})
    except MerchantPasswordReset.DoesNotExist:
        return JsonResponse({"detail": "Link inválido ou expirado."}, status=400)
