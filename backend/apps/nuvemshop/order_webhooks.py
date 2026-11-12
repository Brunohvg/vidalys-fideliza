"""Entrada autenticada e idempotente dos avisos de pedidos Nuvemshop.

HMAC é verificado antes de ler JSON. Cada linha persistida contém apenas
identificadores operacionais mínimos e nunca autoriza cashback ou pedidos.
"""
import hashlib
import json
import logging
import os

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Tenant, TenantMembership
from .models import NuvemshopInstallation
from .order_webhook_models import OrderWebhookEvent
from .privacy_webhooks import _check_hmac, _positive_id, MAX_WEBHOOK_BYTES
from .scopes import has_order_access
from .views import member_for

logger = logging.getLogger(__name__)
TOPICS = {
    "paid": OrderWebhookEvent.Topic.PAID,
    "updated": OrderWebhookEvent.Topic.UPDATED,
}


def _decode_order_event(body, topic):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("event") != topic:
        return None
    store_id = _positive_id(payload.get("store_id"))
    order_id = _positive_id(payload.get("id"))
    event_launch_ts = _positive_id(payload.get("event_launch_ts"))
    if not all((store_id, order_id, event_launch_ts)):
        return None
    timestamp = int(event_launch_ts)
    if timestamp > 9223372036854775807:
        return None
    return store_id, order_id, timestamp


def _response():
    result = JsonResponse({"received": True}, status=202)
    result["Cache-Control"] = "no-store"
    result["X-Robots-Tag"] = "noindex, nofollow"
    return result


@csrf_exempt
@require_POST
@never_cache
def order_webhook(request, kind):
    topic = TOPICS.get(kind)
    if topic is None:
        return HttpResponse(status=404)
    if not settings.FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED:
        return HttpResponse(status=503)
    if request.content_type != "application/json":
        return HttpResponse(status=415)
    length = request.META.get("CONTENT_LENGTH", "")
    if length:
        try:
            if int(length) < 0 or int(length) > MAX_WEBHOOK_BYTES:
                return HttpResponse(status=413)
        except ValueError:
            return HttpResponse(status=400)
    body = request.body
    if len(body) > MAX_WEBHOOK_BYTES:
        return HttpResponse(status=413)
    valid = _check_hmac(body, request.headers.get("X-Linkedstore-Hmac-Sha256", ""))
    if valid is None:
        return HttpResponse(status=503)
    if not valid:
        return HttpResponse(status=401)
    parsed = _decode_order_event(body, topic)
    if parsed is None:
        return HttpResponse(status=400)
    store_id, order_id, launched = parsed
    client_id = _positive_id(os.getenv("NUVEMSHOP_CLIENT_ID", ""))
    if not client_id:
        return HttpResponse(status=503)
    # A identidade do evento é semântica: atributos extras ou contador de
    # reentregas não geram nova linha. Um update posterior tem outro timestamp.
    canonical = f"order-webhook:v1:{client_id}:{store_id}:{topic}:{order_id}:{launched}"
    dedupe_key = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    try:
        with transaction.atomic():
            tenant = Tenant.objects.select_for_update().filter(
                platform="nuvemshop", external_store_id=store_id,
                status=Tenant.Status.ACTIVE,
            ).first()
            if tenant is None:
                return _response()  # Uma loja não vinculada não pode gerar eventos locais.
            valid_installation = NuvemshopInstallation.objects.filter(
                tenant=tenant, store_id=store_id, client_id=client_id,
            ).first()
            if not valid_installation or not has_order_access(
                valid_installation.scope, preview_enabled=True
            ):
                return _response()
            OrderWebhookEvent.objects.get_or_create(
                dedupe_key=dedupe_key,
                defaults={
                    "tenant": tenant,
                    "store_id": store_id,
                    "order_id": order_id,
                    "topic": topic,
                    "event_launch_ts": launched,
                },
            )
        return _response()
    except Exception:
        # Não gravar payload, exceção ou identificadores no log.
        logger.warning("Recepção de evento de pedido pendente de reentrega")
        return HttpResponse(status=503)


class OrderEventsView(APIView):
    """Caixa de entrada visível apenas ao administrador da própria loja."""
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request, tenant_id):
        member = member_for(request.user, tenant_id)
        tenant = member.tenant
        if member.role not in (TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN):
            return self._answer({"detail": "Acesso restrito."}, 403)
        if not settings.FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED:
            return self._answer({"detail": "Eventos de pedidos desativados."}, 409)
        client_id = _positive_id(os.getenv("NUVEMSHOP_CLIENT_ID", ""))
        installed = NuvemshopInstallation.objects.filter(
            tenant=tenant, store_id=tenant.external_store_id,
            client_id=client_id,
        ).first() if client_id else None
        if (tenant.status != Tenant.Status.ACTIVE or tenant.platform != "nuvemshop"
                or not installed or not has_order_access(installed.scope, preview_enabled=True)):
            return self._answer({"detail": "Integração de pedidos indisponível."}, 409)
        items = OrderWebhookEvent.objects.filter(tenant=tenant).only(
            "id", "order_id", "topic", "received_at", "event_launch_ts",
        )[:20]
        return self._answer({
            "mode": "read_only",
            "requires_payment_reconciliation": True,
            "cashback_credited": False,
            "items": [{
                "id": str(item.id),
                "order_id": item.order_id,
                "event": item.topic,
                "received_at": item.received_at.isoformat(),
                "event_launch_ts": item.event_launch_ts,
                "state": "pending_reconciliation",
            } for item in items],
        })

    @staticmethod
    def _answer(data, status=200):
        response = Response(data, status=status)
        response["Cache-Control"] = "private, no-store"
        return response
