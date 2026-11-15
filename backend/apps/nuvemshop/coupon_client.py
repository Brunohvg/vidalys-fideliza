"""Admin API 2025-03: um cupom único por voucher, HTTP fail-closed.

Sem redirect com Bearer; POST sem retry automático (evita duplicação em timeout).
GET por código apenas para reconciliação de resultado desconhecido.
"""
import json
import re
from datetime import timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from apps.catalog.client import API_ROOT
from .order_readonly import safe_id


class CouponRemoteError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(*, store_id, token, agent, method, path, payload=None, opener=None):
    sid = safe_id(store_id)
    if not sid or not isinstance(token, str) or not 16 <= len(token) <= 4096:
        raise CouponRemoteError("Instalação OAuth não autorizada")
    if not isinstance(agent, str) or not 4 <= len(agent) <= 150:
        raise CouponRemoteError("User-Agent inválido")
    headers = {"Authorization": "Bearer " + token, "User-Agent": agent,
               "Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(f"{API_ROOT}/{sid}/{path}", method=method,
                      headers=headers, data=body)
    try:
        with (opener or build_opener(NoRedirect())).open(request, timeout=8) as response:
            result = response.read(131073)
            if len(result) > 131072:
                raise CouponRemoteError("Resposta do cupom excede limite")
            status = response.status
            if status not in (200, 201):
                raise CouponRemoteError("HTTP inesperado ao consultar cupom")
            return json.loads(result, parse_float=str)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise CouponRemoteError("Resultado de operação Nuvemshop requer conferência") from None
    except (ValueError, UnicodeError):
        raise CouponRemoteError("Resposta de cupom inválida") from None


def coupon_payload(*, code, discount_cents, min_order_cents, expires_at):
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9]{20,50}", code):
        raise CouponRemoteError("Código externo inválido")
    if (type(discount_cents) is not int or not 0 < discount_cents <= 100_000_000
            or type(min_order_cents) is not int or min_order_cents < discount_cents):
        raise CouponRemoteError("Valores da recompensa inválidos")
    if not expires_at or expires_at.tzinfo is None:
        raise CouponRemoteError("Expiração do voucher obrigatória")
    # API 2025-03 recebe end_date YYYY-MM-DD + end_time HH:MM,
    # nunca ISO-8601 completo. Sem `tz=store` o provedor usa UTC.
    until = expires_at.astimezone(timezone.utc)
    return {
        "code": code, "type": "absolute",
        "value": f"{Decimal(discount_cents)/100:.2f}",
        "max_uses": 1, "min_price": f"{Decimal(min_order_cents)/100:.2f}",
        "includes_shipping": False, "combines_with_other_discounts": False,
        "end_date": until.strftime("%Y-%m-%d"),
        "end_time": until.strftime("%H:%M"),
    }


def verify_coupon(remote, expected):
    if not isinstance(remote, dict) or safe_id(remote.get("id")) is None:
        raise CouponRemoteError("Cupom não possui ID válido")
    if (remote.get("code") != expected["code"]
            or remote.get("type") != "absolute"
            or type(remote.get("max_uses")) is not int
            or remote["max_uses"] != 1):
        raise CouponRemoteError("Cupom de outra configuração não pode ser vinculado")
    try:
        actual = Decimal(str(remote.get("value")))
        minimum = Decimal(str(remote.get("min_price")))
    except (InvalidOperation, TypeError, ValueError):
        raise CouponRemoteError("Valores remotos inconsistentes") from None
    if actual != Decimal(expected["value"]) or minimum != Decimal(expected["min_price"]):
        raise CouponRemoteError("Cupom externo divergente do voucher")
    if (remote.get("includes_shipping") is not False
            or remote.get("combines_with_other_discounts") is not False
            or remote.get("end_date") != expected["end_date"]
            or remote.get("end_time") != expected["end_time"]):
        raise CouponRemoteError("Cupom remoto não preservou regras comerciais")
    return str(remote["id"])


def find_coupon_exact(*, store_id, token, agent, expected, opener=None):
    query = urlencode({"q": expected["code"], "per_page": 20})
    found = _transport(store_id=store_id, token=token, agent=agent,
                       method="GET", path="coupons?" + query, opener=opener)
    if not isinstance(found, list):
        raise CouponRemoteError("Lista remota inesperada")
    matches = [x for x in found if isinstance(x, dict)
               and x.get("code") == expected["code"]]
    if not matches:
        return None
    if len(matches) != 1:
        raise CouponRemoteError("Código remoto não único")
    return verify_coupon(matches[0], expected)


def create_coupon_once(*, store_id, token, agent, expected, opener=None):
    remote = _transport(store_id=store_id, token=token, agent=agent,
                        method="POST", path="coupons", payload=expected, opener=opener)
    return verify_coupon(remote, expected)
