"""Pagar.me v5: proof by authenticated GET, never trust a webhook body.

Basic secret key is only used against the fixed HTTPS charges endpoint.
Charge identifier must be anchored to the exact commerce order reference.
"""
import base64
import json
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener
from django.utils.dateparse import parse_datetime


class PaymentProviderError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


CHARGE_ID = re.compile(r"^ch_[A-Za-z0-9]{8,80}$")


def fetch_charge(*, charge_id, secret_key, opener=None):
    if not isinstance(charge_id, str) or not CHARGE_ID.fullmatch(charge_id):
        raise PaymentProviderError("ID de cobrança inválido")
    if (not isinstance(secret_key, str) or len(secret_key) < 12
            or not secret_key.startswith(("sk_test_", "sk_"))):
        raise PaymentProviderError("Chave PSP ausente")
    auth = base64.b64encode((secret_key + ":").encode()).decode("ascii")
    req = Request(
        "https://api.pagar.me/core/v5/charges/" + charge_id,
        headers={"Authorization": "Basic " + auth, "Accept": "application/json"},
        method="GET",
    )
    try:
        with (opener or build_opener(_NoRedirect())).open(req, timeout=8) as response:
            raw = response.read(131073)
            if len(raw) > 131072:
                raise PaymentProviderError("Resposta PSP excede limite")
            data = json.loads(raw, parse_float=str)
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError):
        raise PaymentProviderError("Não foi possível conferir a cobrança no PSP") from None
    if not isinstance(data, dict):
        raise PaymentProviderError("Resposta PSP inválida")
    return data


def validate_paid_charge(*, charge, charge_id, order_reference, total_cents):
    """Strong binding: paid charge, exact order.code, amount and timestamp.

    Never attempt to infer mapping from amount, customer name or proximity.
    """
    if (not isinstance(charge, dict) or charge.get("id") != charge_id
            or charge.get("status") != "paid"):
        raise PaymentProviderError("Cobrança não liquidada")
    order = charge.get("order")
    if (not isinstance(order, dict)
            or order.get("code") != order_reference):
        raise PaymentProviderError("Cobrança não pertence à referência do pedido")
    amount = charge.get("amount")
    paid = charge.get("paid_amount")
    if (type(amount) is not int or type(paid) is not int
            or amount != total_cents or paid != total_cents
            or total_cents <= 0):
        raise PaymentProviderError("Valor liquidado divergente")
    paid_at = charge.get("paid_at")
    when = parse_datetime(paid_at) if isinstance(paid_at, str) else None
    if not isinstance(when, datetime) or when.tzinfo is None:
        raise PaymentProviderError("Data de pagamento autenticada ausente")
    return when
