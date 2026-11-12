"""Autenticação de sessão Django para interface comercial.

Sem OAuth Nuvemshop e sem credenciais demo. Operações mutáveis exigem CSRF.
Proteção de tentativas por usuário utiliza cache Redis em homologação.
O proxy também deve aplicar limite por IP antes de publicar externamente.
"""

import hashlib
import json
import logging

from django.contrib.auth import authenticate, login, logout
from .merchant_auth import account_for_email, normalize_email
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST

from apps.tenants.models import TenantMembership

logger = logging.getLogger(__name__)
MAX_FAILURES = 8
WINDOW_SECONDS = 15 * 60


def _memberships(user):
    return list(
        TenantMembership.objects.filter(user=user)
        .select_related("tenant").order_by("tenant__name")
        .values("tenant__id", "tenant__name", "tenant__slug", "tenant__status", "role")
    )


def _public_tenants(user):
    return [
        {
            "id": str(record["tenant__id"]),
            "name": record["tenant__name"],
            "slug": record["tenant__slug"],
            "status": record["tenant__status"],
            "role": record["role"],
        }
        for record in _memberships(user)
    ]


@never_cache
@ensure_csrf_cookie
@require_GET
def session_info(request):
    """Gera csrftoken em cookie, sem expor token no corpo."""
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False, "user": None, "tenants": []})
    return JsonResponse({
        "authenticated": True,
        "user": {
            "username": request.user.get_username(),
            "display_name": request.user.get_full_name() or request.user.get_username(),
        },
        "tenants": _public_tenants(request.user),
    })


def _json(request):
    if not request.content_type.startswith("application/json"):
        return None
    if len(request.body) > 4096:
        return None
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _throttle_key(username):
    digest = hashlib.sha256(username.casefold().encode("utf-8")).hexdigest()
    return f"fideliza:login-fails:{digest}"


@never_cache
@sensitive_post_parameters("password")
@csrf_protect
@require_POST
def login_session(request):
    data = _json(request)
    if data is None:
        return JsonResponse({"detail": "Envie um JSON válido."}, status=400)

    email = data.get("email")
    # Compatibilidade temporaria: usuarios tecnicos antigos podem usar username.
    username = data.get("username") if email is None else None
    password = data.get("password")
    if (not isinstance(password, str) or
        not isinstance(email if email is not None else username, str)):
        return JsonResponse({"detail": "Informe e-mail e senha."}, status=400)
    identifier = email if email is not None else username
    identifier = identifier.strip().casefold()
    if not 1 <= len(identifier) <= 254 or not 1 <= len(password) <= 4096:
        return JsonResponse({"detail": "Credenciais inválidas."}, status=400)
    key = _throttle_key(identifier)
    failures = cache.get(key, 0)
    if failures >= MAX_FAILURES:
        return JsonResponse(
            {"detail": "Limite de tentativas atingido. Tente novamente mais tarde."},
            status=429,
        )

    if email is not None:
        try:
            normalized = normalize_email(identifier)
            matched = account_for_email(normalized)
        except ValidationError:
            matched = None
        user = (authenticate(request=request, username=matched.get_username(),
                             password=password) if matched else None)
    else:
        user = authenticate(request=request, username=identifier, password=password)
    if user is None or not user.is_active:
        if cache.add(key, 1, timeout=WINDOW_SECONDS) is False:
            cache.incr(key)
        logger.warning("Falha de autenticação da conta %s", key[-12:])
        return JsonResponse({"detail": "Usuário ou senha inválidos."}, status=401)

    cache.delete(key)
    login(request, user)
    return JsonResponse({"authenticated": True, "tenants": _public_tenants(user)})


@never_cache
@csrf_protect
@require_POST
def logout_session(request):
    if request.user.is_authenticated:
        logout(request)
    return JsonResponse({"authenticated": False})
