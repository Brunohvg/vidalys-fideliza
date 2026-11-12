"""Consulta isolada de pedido Nuvemshop (API 2025-03), sem escrita."""
import json
import time
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from django.utils.dateparse import parse_datetime
from apps.catalog.client import API_ROOT

class OrderReadError(RuntimeError):
    pass

class OrderNotFound(OrderReadError):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

FIELDS = "id,status,payment_status,paid_at,cancelled_at,total,currency,gateway,customer"

def safe_id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value)
    if not text.isascii() or not text.isdecimal() or len(text) > 18:
        return None
    return str(int(text)) if int(text) > 0 else None

def read_order(*, store_id, order_id, access_token, user_agent, opener=None, pause=time.sleep):
    if not safe_id(store_id) or not safe_id(order_id):
        raise ValueError("Identificador inválido")
    if not isinstance(access_token, str) or not 16 <= len(access_token) <= 4096:
        raise ValueError("Credencial ausente")
    if not isinstance(user_agent, str) or not 4 <= len(user_agent) <= 150:
        raise ValueError("User-Agent inválido")
    request = Request(
        f"{API_ROOT}/{store_id}/orders/{order_id}?fields={FIELDS}",
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": user_agent,
                 "Accept": "application/json"},
        method="GET",
    )
    transport = opener or build_opener(NoRedirect())
    for attempt in range(3):
        try:
            with transport.open(request, timeout=8) as result:
                body = result.read(262145)
                if len(body) > 262144:
                    raise OrderReadError("Resposta muito grande")
                data = json.loads(body, parse_float=str)
                if not isinstance(data, dict):
                    raise OrderReadError("Pedido inesperado")
                return data
        except HTTPError as exc:
            if exc.code == 404:
                raise OrderNotFound("Não encontrado") from None
            if exc.code in (429, 502, 503, 504) and attempt < 2:
                pause(min(attempt + 1, 2))
                continue
            raise OrderReadError("Consulta indisponível") from None
        except (URLError, TimeoutError, OSError):
            if attempt < 2:
                pause(min(attempt + 1, 2))
                continue
            raise OrderReadError("Conexão indisponível") from None
        except (UnicodeError, json.JSONDecodeError):
            raise OrderReadError("Resposta inválida") from None
    raise OrderReadError("Tentativas esgotadas")

def summarize_order(data, *, order_id, participant_verified=False):
    """Normaliza somente fatos não pessoais; nunca concede cashback."""
    if not isinstance(data, dict) or safe_id(data.get("id")) != str(order_id):
        raise OrderReadError("Pedido divergente")
    status, payment = data.get("status"), data.get("payment_status")
    if status not in ("open", "closed", "cancelled") or payment not in (
        "pending", "authorized", "paid", "partially_paid", "abandoned",
        "refunded", "partially_refunded", "voided",
    ):
        raise OrderReadError("Status desconhecido")
    currency = data.get("currency")
    try:
        amount = Decimal(str(data.get("total")))
    except (InvalidOperation, TypeError, ValueError):
        raise OrderReadError("Valor inválido") from None
    if (not amount.is_finite() or amount < 0 or amount > Decimal("1000000000")
            or amount * 100 != (amount * 100).to_integral_value()
            or not isinstance(currency, str) or len(currency) != 3
            or not currency.isascii() or not currency.isalpha()):
        raise OrderReadError("Montante inválido")
    raw_date = data.get("paid_at")
    paid_at = parse_datetime(raw_date) if isinstance(raw_date, str) else None
    if paid_at is not None and paid_at.tzinfo is None:
        paid_at = None
    if status == "cancelled" or data.get("cancelled_at"):
        state = "blocked_cancelled"
    elif payment in ("refunded", "partially_refunded"):
        state = "blocked_refund"
    elif payment != "paid":
        state = "not_paid"
    elif not paid_at:
        state = "payment_date_missing"
    elif not participant_verified:
        state = "customer_not_verified"
    elif data.get("gateway") in ("internal", "offline", "not-provided", None, ""):
        state = "manual_payment_review"
    else:
        state = "reported_paid_requires_reconciliation"
    return {
        "order_id": str(order_id), "source": "nuvemshop_live_read_only",
        "order_status": status, "payment_status": payment,
        "paid_at": paid_at.isoformat() if paid_at else None,
        "reported_total_cents": int(amount * 100), "currency": currency.upper(),
        "participant_verified": bool(participant_verified),
        "review_status": state, "credit_eligible": False,
        "cashback_created": False, "writes_performed": 0,
        "note": "Pagamento reportado ainda exige conciliação, reversões e auditoria.",
    }
