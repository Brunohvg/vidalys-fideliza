"""Webhook assinado app/uninstalled: encerra a instalação na hora.

O store/redact (LGPD) chega depois e apaga os dados. Até lá, uma
instalação desinstalada não pode aparecer como conectada, receber
eventos de pedido nem disparar releituras com token revogado.
Nada aqui apaga registros, credita ou estorna valores.
"""
import json
import logging
import os

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import NuvemshopInstallation
from .privacy_webhooks import MAX_WEBHOOK_BYTES, _check_hmac, _positive_id

logger = logging.getLogger(__name__)
TOPICS = {"uninstalled": "app/uninstalled"}


def _accepted():
    result = JsonResponse({"received": True}, status=202)
    result["Cache-Control"] = "no-store"
    result["X-Robots-Tag"] = "noindex, nofollow"
    return result


def _store_from(body, topic):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("event") not in (None, topic):
        return None
    return _positive_id(payload.get("store_id"))


@csrf_exempt
@require_POST
@never_cache
def app_webhook(request, kind):
    topic = TOPICS.get(kind)
    if topic is None:
        return HttpResponse(status=404)
    if request.content_type != "application/json":
        return HttpResponse(status=415)
    body = request.body
    if len(body) > MAX_WEBHOOK_BYTES:
        return HttpResponse(status=413)
    valid = _check_hmac(body, request.headers.get("X-Linkedstore-Hmac-Sha256", ""))
    if valid is None:
        return HttpResponse(status=503)
    if not valid:
        return HttpResponse(status=401)
    store_id = _store_from(body, topic)
    if store_id is None:
        return HttpResponse(status=400)
    client_id = _positive_id(os.getenv("NUVEMSHOP_CLIENT_ID", ""))
    if not client_id:
        return HttpResponse(status=503)
    try:
        with transaction.atomic():
            # Idempotente: retries mantêm a primeira data registrada.
            NuvemshopInstallation.objects.filter(
                client_id=client_id, store_id=store_id,
                uninstalled_at__isnull=True,
            ).update(uninstalled_at=timezone.now())
        return _accepted()
    except Exception:
        logger.warning("Aviso de desinstalação pendente de reentrega")
        return HttpResponse(status=503)
