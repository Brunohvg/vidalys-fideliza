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

FIELDS = "id,number,status,payment_status,paid_at,cancelled_at,total,total_paid_by_customer,currency,gateway,customer"

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

def read_orders_page(*, store_id, access_token, user_agent, opener=None, pause=time.sleep):
    """Primeira página oficial, limitada a 10 pedidos. Nunca grava e nunca expõe PII."""
    if not safe_id(store_id):
        raise ValueError("Loja inválida")
    if not isinstance(access_token,str) or not 16 <= len(access_token) <= 4096:
        raise ValueError("Credencial ausente")
    if not isinstance(user_agent,str) or not 4 <= len(user_agent) <= 150:
        raise ValueError("User-Agent inválido")
    request=Request(
        f"{API_ROOT}/{store_id}/orders?page=1&per_page=10&fields={FIELDS}",
        headers={"Authorization":f"Bearer {access_token}",
                 "User-Agent":user_agent,"Accept":"application/json"},method="GET",
    )
    transport=opener or build_opener(NoRedirect())
    for attempt in range(3):
        try:
            with transport.open(request,timeout=8) as response:
                body=response.read(262145)
                if len(body)>262144:
                    raise OrderReadError("Lista de pedidos muito grande")
                data=json.loads(body,parse_float=str)
                if not isinstance(data,list) or len(data)>10:
                    raise OrderReadError("Lista de pedidos inesperada")
                if any(not isinstance(item,dict) for item in data):
                    raise OrderReadError("Pedido na lista inválido")
                return data
        except HTTPError as exc:
            if exc.code in (429,502,503,504) and attempt<2:
                pause(min(attempt+1,2))
                continue
            raise OrderReadError("Consulta de pedidos indisponível") from None
        except (URLError,TimeoutError,OSError):
            if attempt<2:
                pause(min(attempt+1,2))
                continue
            raise OrderReadError("Conexão indisponível") from None
        except (UnicodeError,json.JSONDecodeError):
            raise OrderReadError("Lista de pedidos inválida") from None
    raise OrderReadError("Tentativas esgotadas")


def read_order_by_number(*, store_id, number, access_token, user_agent,
                         opener=None, pause=time.sleep):
    """Busca pelo número comercial e exige correspondência EXATA dentro da loja.

    q também permite buscar por nome/email; nunca confiar em um match parcial.
    Após resolver o id, busca novamente os dados atuais por GET /orders/{id}.
    """
    if not safe_id(store_id) or not safe_id(number):
        raise ValueError("Número de pedido inválido")
    if not isinstance(access_token, str) or not 16 <= len(access_token) <= 4096:
        raise ValueError("Credencial ausente")
    if not isinstance(user_agent, str) or not 4 <= len(user_agent) <= 150:
        raise ValueError("User-Agent inválido")
    request = Request(
        f"{API_ROOT}/{store_id}/orders?q={safe_id(number)}&per_page=10&fields=id,number",
        headers={"Authorization":f"Bearer {access_token}",
                 "User-Agent":user_agent,"Accept":"application/json"},
        method="GET",
    )
    transport = opener or build_opener(NoRedirect())
    matches = []
    for attempt in range(3):
        try:
            with transport.open(request, timeout=8) as result:
                body = result.read(65537)
                if len(body) > 65536:
                    raise OrderReadError("Lista de pedidos muito grande")
                data = json.loads(body)
                if not isinstance(data, list) or len(data) > 10:
                    raise OrderReadError("Lista de pedidos inesperada")
                matches = [
                    item for item in data
                    if isinstance(item, dict) and safe_id(item.get("number")) == safe_id(number)
                    and safe_id(item.get("id"))
                ]
                break
        except HTTPError as exc:
            if exc.code == 404:
                raise OrderNotFound("Pedido não encontrado") from None
            if exc.code in (429, 502, 503, 504) and attempt < 2:
                pause(min(attempt+1,2))
                continue
            raise OrderReadError("Consulta de pedidos indisponível") from None
        except (URLError,TimeoutError,OSError):
            if attempt < 2:
                pause(min(attempt+1,2))
                continue
            raise OrderReadError("Conexão indisponível") from None
        except (UnicodeError,json.JSONDecodeError):
            raise OrderReadError("Lista de pedidos inválida") from None
    if len(matches) == 0:
        raise OrderNotFound("Número comercial não encontrado nesta loja")
    if len(matches) != 1:
        raise OrderReadError("Número comercial ambíguo; informe o link do pedido")
    return read_order(
        store_id=store_id,order_id=safe_id(matches[0]["id"]),
        access_token=access_token,user_agent=user_agent,
        opener=opener,pause=pause,
    )


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
    # O valor recebido informado pela própria Nuvemshop pode divergir de
    # 'total' por pagamentos parciais, taxas, edições ou pedidos sem
    # transação. Isso NÃO é uma confirmação independente do gateway.
    reported_paid_cents = None
    if data.get("total_paid_by_customer") is not None:
        try:
            amount_paid = Decimal(str(data["total_paid_by_customer"]))
        except (InvalidOperation, TypeError, ValueError):
            raise OrderReadError("Pagamento reportado inválido") from None
        if (not amount_paid.is_finite() or amount_paid < 0
                or amount_paid > Decimal("1000000000")
                or amount_paid * 100 != (amount_paid * 100).to_integral_value()):
            raise OrderReadError("Pagamento reportado inválido")
        reported_paid_cents = int(amount_paid * 100)
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
    elif reported_paid_cents is not None and reported_paid_cents != int(amount * 100):
        # Divergência deve ser revisada, nunca usada como base de cashback.
        state = "reported_paid_amount_review"
    else:
        state = "reported_paid_requires_reconciliation"
    number = data.get("number")
    order_number = safe_id(number) if number is not None else None
    if number is not None and order_number is None:
        raise OrderReadError("Número comercial do pedido inválido")
    return {
        "order_id": str(order_id), "order_number": order_number,
        "source": "nuvemshop_live_read_only",
        "order_status": status, "payment_status": payment,
        "paid_at": paid_at.isoformat() if paid_at else None,
        "reported_total_cents": int(amount * 100), "currency": currency.upper(),
        "reported_customer_paid_cents": reported_paid_cents,
        "reported_payment_differs_from_total": (
            None if reported_paid_cents is None
            else reported_paid_cents != int(amount * 100)
        ),
        "reported_paid_amount_is_not_psp_proof": True,
        "participant_verified": bool(participant_verified),
        "review_status": state, "credit_eligible": False,
        "cashback_created": False, "writes_performed": 0,
        "note": "Pagamento reportado ainda exige conciliação, reversões e auditoria.",
    }
