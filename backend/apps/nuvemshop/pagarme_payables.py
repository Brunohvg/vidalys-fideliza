"""Pagar.me v5 receivables: authoritative fee reconciliation, no webhooks.

GET /core/v5/payables?charge_id=... uses cursor paging (2026 API change).
The charge GET alone is not a fee receipt. Never silently assume zero fees.
"""
import base64
import hashlib
import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from .pagarme_payment import CHARGE_ID, PaymentProviderError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class VerifiedPspFees:
    gross_cents: int
    fee_cents: int
    net_cents: int
    snapshot_digest: str
    count: int


def fetch_payables(*, charge_id, secret_key, opener=None, max_pages=8):
    """GET authenticated pages; return only a complete bounded snapshot."""
    if not isinstance(charge_id, str) or not CHARGE_ID.fullmatch(charge_id):
        raise PaymentProviderError("Cobrança PSP inválida")
    if (not isinstance(secret_key, str) or not secret_key.startswith(("sk_","sk_test_"))
            or len(secret_key) < 12):
        raise PaymentProviderError("Chave PSP ausente")
    auth = base64.b64encode((secret_key+":").encode("utf-8")).decode("ascii")
    cursor = None
    seen_cursors = set()
    pages = []
    for _ in range(max_pages):
        query = {"charge_id": charge_id, "size": 100}
        if cursor:
            query["forward_cursor"] = cursor
        req = Request(
            "https://api.pagar.me/core/v5/payables?" + urlencode(query),
            headers={"Authorization": "Basic " + auth, "Accept": "application/json"},
            method="GET",
        )
        try:
            with (opener or build_opener(_NoRedirect())).open(req, timeout=8) as response:
                if response.status != 200:
                    raise PaymentProviderError("HTTP da consulta de recebíveis inválido")
                body = response.read(262145)
                if len(body) > 262144:
                    raise PaymentProviderError("Resposta PSP excessiva")
                parsed = json.loads(body)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeError):
            raise PaymentProviderError("Recebíveis PSP indisponíveis") from None
        if not isinstance(parsed, dict) or not isinstance(parsed.get("data"), list):
            raise PaymentProviderError("Resposta financeira PSP malformada")
        pages.extend(parsed["data"])
        if len(pages) > 800:
            raise PaymentProviderError("Consulta financeira excedeu limite")
        paging = parsed.get("paging")
        if not isinstance(paging, dict):
            raise PaymentProviderError("Paginação de recebíveis não comprovada")
        next_cursor = paging.get("forward_cursor")
        if not next_cursor:
            return pages
        if (not isinstance(next_cursor, str)
                or len(next_cursor) > 400 or next_cursor in seen_cursors):
            raise PaymentProviderError("Paginação PSP incorreta")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    raise PaymentProviderError("Recebíveis PSP com paginação incompleta")


def verify_payables(*, payables, charge_id, captured_cents, recipient_id):
    """Complete, non-split, paid credit payables only; no uncertain fee numbers."""
    if (not isinstance(payables, list) or not payables or len(payables) > 800
            or not isinstance(recipient_id, str)
            or not re.fullmatch(r"re_[a-zA-Z0-9]{6,100}", recipient_id)):
        raise PaymentProviderError("Recebíveis completos ou recebedor não comprovados")
    ids = set()
    gross = fees = 0
    canonical = []
    for payable in payables:
        if not isinstance(payable, dict):
            raise PaymentProviderError("Recebível inválido")
        ident = payable.get("id")
        if (not isinstance(ident, (str,int)) or isinstance(ident,bool)
                or not str(ident) or str(ident) in ids):
            raise PaymentProviderError("Recebível duplicado ou sem identificação")
        ids.add(str(ident))
        if (payable.get("charge_id") != charge_id
                or payable.get("recipient_id") != recipient_id
                or payable.get("type") != "credit"
                or payable.get("status") != "paid"
                or payable.get("split_id") not in (None,"")
                or payable.get("originator_model") not in (None,"")):
            raise PaymentProviderError("Recebível não liquidado ou divergente da loja")
        amount = payable.get("amount")
        fee = payable.get("fee")
        anticipation = payable.get("anticipation_fee")
        fraud = payable.get("fraud_coverage_fee")
        if (any(type(n) is not int or n < 0 for n in (amount, fee, anticipation, fraud))
                or amount <= 0 or fee+anticipation+fraud > amount):
            raise PaymentProviderError("Taxas financeiras incompletas")
        gross += amount
        fees += fee+anticipation+fraud
        canonical.append((str(ident),amount,fee,anticipation,fraud))
    if (type(captured_cents) is not int or gross != captured_cents
            or not 0 <= fees < gross):
        raise PaymentProviderError("Bruto, líquido ou taxa PSP divergente")
    digest = hashlib.sha256(json.dumps(
        sorted(canonical), separators=(",",":"),ensure_ascii=True,
    ).encode()).hexdigest()
    return VerifiedPspFees(
        gross_cents=gross, fee_cents=fees,
        net_cents=gross-fees, snapshot_digest=digest,
        count=len(payables),
    )
