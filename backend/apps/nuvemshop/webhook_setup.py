"""Cadastro automático dos avisos de pedido (webhooks) na loja Nuvemshop conectada.

Sem eles a loja nunca avisa que um pedido foi pago, cancelado ou reembolsado, e o clube do
site não funciona. Por isso, ao conectar (ou "Atualizar conexão") a loja, o sistema confere
`GET /webhooks` e cria só o que falta com `POST /webhooks {event, url}`. Nunca apaga avisos
de terceiros. A URL sai do domínio do callback OAuth (a própria API), sempre HTTPS.

Só roda com FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED ligado (avisos para um receptor
desligado gerariam falhas na Nuvemshop) e com permissão de pedidos aceita.
Token só aqui: API ou worker isolado (fila "nuvemshop").
"""
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from django.conf import settings

logger = logging.getLogger(__name__)

NEEDED = (("order/paid", "paid"), ("order/updated", "updated"))   # updated traz cancelado/reembolsado


class WebhookSetupError(RuntimeError):
    pass


def receiver_url(callback_url, kind):
    parsed = urlsplit(callback_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise WebhookSetupError("Callback OAuth sem HTTPS")
    return f"https://{parsed.netloc}/api/v1/webhooks/orders/{kind}/"


def _credentials(tenant):
    from .models import NuvemshopInstallation
    from .order_readonly import safe_id
    from .security import config, decrypt_token
    cfg = config()
    installed = NuvemshopInstallation.objects.get(tenant=tenant, client_id=cfg.client_id)
    sid = safe_id(installed.store_id)
    if not sid:
        raise WebhookSetupError("Loja inválida")
    return sid, decrypt_token(installed.token_ciphertext, cfg.token_keys), cfg.user_agent, cfg.callback_url, installed.scope


def _api(store_id, token, agent, method, payload=None, opener=None):
    from apps.catalog.client import API_ROOT
    from .coupon_client import NoRedirect
    headers = {"Authorization": "Bearer " + token, "User-Agent": agent, "Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, separators=(",", ":")).encode()
    path = "webhooks?per_page=200" if method == "GET" else "webhooks"
    request = Request(f"{API_ROOT}/{store_id}/{path}", method=method, headers=headers, data=body)
    try:
        with (opener or build_opener(NoRedirect())).open(request, timeout=10) as response:
            data = response.read(262145)
            if len(data) > 262144 or response.status not in (200, 201):
                raise WebhookSetupError("Resposta inesperada")
            return json.loads(data)
    except HTTPError as exc:
        if method == "GET" and exc.code == 404 and b"Last page is 0" in exc.read(2048):
            return []                                                   # nenhum aviso cadastrado
        raise WebhookSetupError(f"Nuvemshop respondeu {exc.code}") from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise WebhookSetupError("Nuvemshop não respondeu") from None


def _registered(listing, url_by_event):
    if not isinstance(listing, list):
        raise WebhookSetupError("Lista de avisos inesperada")
    found = {(w.get("event"), w.get("url")) for w in listing if isinstance(w, dict)}
    return {event: (event, url) in found for event, url in url_by_event.items()}


def order_webhooks(tenant, *, ensure=False, opener=None):
    """{evento: "ok" | "created" | "missing"} ou {"_skipped": motivo}. Levanta em falha de rede."""
    from .scopes import has_order_access
    if not getattr(settings, "FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED", False):
        return {"_skipped": "receiver_off"}
    store_id, token, agent, callback, scope = _credentials(tenant)
    if not has_order_access(scope, preview_enabled=True):
        return {"_skipped": "no_order_scope"}
    urls = {event: receiver_url(callback, kind) for event, kind in NEEDED}
    present = _registered(_api(store_id, token, agent, "GET", opener=opener), urls)
    result = {}
    for event, url in urls.items():
        if present[event]:
            result[event] = "ok"
        elif ensure:
            created = _api(store_id, token, agent, "POST", {"event": event, "url": url}, opener=opener)
            if not isinstance(created, dict) or created.get("event") != event or created.get("url") != url:
                raise WebhookSetupError("Aviso criado com dados divergentes")
            result[event] = "created"
        else:
            result[event] = "missing"
    logger.info("nuvemshop order_webhooks tenant=%s result=%s", tenant.pk,
                ",".join(f"{k}:{v}" for k, v in sorted(result.items())))
    return result
