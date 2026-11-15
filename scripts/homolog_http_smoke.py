#!/usr/bin/env python3
"""Smoke HTTP HTTPS real. Sem mock; modo padrão somente GET e sem credencial.

--write envia somente eventos sintéticos para tenant QA previamente autorizado.
NÃO cria cliente nem comprova pagamento; usa telefone previamente verificado.
"""
import json
import os
import re
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import (
    HTTPRedirectHandler, Request, build_opener, HTTPSHandler,
)

APPROVED_HOST = "fideliza-homolog.optarys.com.br"


class GateFailed(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, url):
        raise GateFailed("Redirecionamento inesperado; não encaminhar token a outro host")


OPENER = build_opener(NoRedirect, HTTPSHandler())


def required(name):
    value = os.environ.get(name, "")
    if not value:
        raise GateFailed(f"Falta {name}")
    return value


def check(condition, message):
    if not condition:
        raise GateFailed(message)


def request(url, method="GET", body=None, token=None, expect=(200,)):
    data = json.dumps(body, separators=(",", ":")).encode("utf8") if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": "vidalys-homolog-smoke/24"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with OPENER.open(req, timeout=12) as response:
            status, raw, mime = response.status, response.read(1024 * 1024), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        status, raw, mime = exc.code, exc.read(1024 * 1024), exc.headers.get("Content-Type", "")
    check(status in expect, f"{method} {urlsplit(url).path} retornou HTTP {status}; esperado {expect}")
    if "application/json" in mime:
        try:
            return status, json.loads(raw)
        except ValueError as exc:
            raise GateFailed("JSON inválido na resposta") from exc
    return status, raw.decode("utf-8", errors="replace")


def main():
    check(os.getenv("FIDELIZA_ENVIRONMENT") == "homolog", "Ambiente não é homolog")
    write = len(sys.argv) == 2 and sys.argv[1] == "--write"
    check(len(sys.argv) == 1 or write, "Uso: script.py [--write]")
    base = required("FIDELIZA_HOMOLOG_BASE_URL").rstrip("/")
    parsed = urlsplit(base)
    check(parsed.scheme == "https" and parsed.hostname == APPROVED_HOST
          and parsed.port is None and not parsed.username and not parsed.password
          and not parsed.path and not parsed.query and not parsed.fragment,
          "URL deve ser o HTTPS EXATO do domínio de homolog")
    slug = required("FIDELIZA_SMOKE_CLUB_SLUG")
    check(bool(re.fullmatch(r"(?:qa|homolog)-[a-z0-9-]{3,52}", slug)),
          "Apenas slug de tenant isolado QA é permitido")
    club_path = quote(slug, safe="")

    _, ready = request(base + "/api/ready/")
    check(isinstance(ready, dict) and ready.get("status") == "ready",
          "Readiness não confirma PostgreSQL")
    _, club = request(base + "/api/v1/public/clubs/" + club_path + "/")
    check(isinstance(club, dict) and club.get("store_slug") == slug,
          "Clube público não corresponde ao tenant QA")
    for flag in ("points_enabled", "rewards_enabled", "redemption_enabled"):
        check(club.get(flag) is False, f"Gate público {flag} não está OFF")
    for reward in club.get("published_rewards", []):
        check(reward.get("redemption_enabled") is False,
              "Recompensa publicada com resgate financeiro indevido")
    status, page = request(base + "/clube/" + club_path,
                           expect=(200,))
    check(isinstance(page, str) and "<html" in page.lower(),
          "SPA do consumidor não retornou HTML")
    status, history = request(base + "/clube/" + club_path + "/historico",
                              expect=(200,))
    check(isinstance(history, str) and "<html" in history.lower(),
          "Rota history não preserva SPA")
    request(base + "/api/v1/public/clubs/" + club_path + "/me/", expect=(401,))
    print("PUBLIC_HTTPS_SMOKE_OK readiness=ready anonymous_member=401 "
          "reward_gate=OFF spa_routes=2")
    if not write:
        print("MODE=READ_ONLY; nenhum pedido foi criado")
        return 0

    check(os.getenv("FIDELIZA_SMOKE_APPROVE_WRITES") == "YES_QA_ONLY",
          "Escrita sintética exige aprovação explícita")
    check(os.getenv("FIDELIZA_SMOKE_TENANT_CHECKED") == "YES_VERIFIED_QA_TENANT",
          "Rode primeiro o verificador privado do tenant QA")
    tenant_id = str(uuid.UUID(required("FIDELIZA_SMOKE_TENANT_ID")))
    token = required("FIDELIZA_SMOKE_FLOW_TOKEN")
    phone = required("FIDELIZA_SMOKE_PHONE_E164")
    check(bool(re.fullmatch(r"\+[1-9]\d{7,14}", phone)), "Telefone QA deve estar em E.164")
    check(len(token) > 36, "Token Flow de homolog não parece válido")

    ref = "PR24-" + uuid.uuid4().hex[:20].upper()
    payload = {
        "tenant_id": tenant_id,
        "channel": "vidalys_flow",
        "external_order_id": ref,
        "customer_identifier": phone,
        "total_amount": "19.90",
        "currency": "BRL",
        "status": "pending",
        "source_event_id": ref + "-P",
    }
    endpoint = base + "/api/v1/events/orders/"
    _, created = request(endpoint, method="POST", body=payload, token=token, expect=(201,))
    check(created.get("created") is True
          and created.get("identity_status") == "verified_contact_match",
          "Ingestão não convergiu para identidade previamente comprovada")
    first_sale = created.get("sale_id")
    first_event = created.get("event_id")
    _, duplicate = request(endpoint, method="POST", body=payload, token=token, expect=(200,))
    check(duplicate.get("duplicate") is True
          and duplicate.get("sale_id") == first_sale
          and duplicate.get("event_id") == first_event,
          "Reenvio não foi idempotente")
    paid = dict(payload, status="paid", source_event_id=ref + "-PAID")
    _, confirmed = request(endpoint, method="POST", body=paid, token=token, expect=(200,))
    check(confirmed.get("sale_id") == first_sale
          and confirmed.get("order_status") == "paid"
          and confirmed.get("loyalty_readiness") == "requires_independent_capture",
          "Estado pago informado não preservou gate de conciliação")
    for result in (created, duplicate, confirmed):
        for flag in ("payment_verified", "points_credited", "cashback_credited"):
            check(result.get(flag) is False, f"{flag} ativado indevidamente")
    print("ORDER_HTTP_SMOKE_OK reference=" + ref +
          " events=2 replays=1 verified_identity=YES financial_credits=OFF")
    print("Execute auditoria de DB com FIDELIZA_SMOKE_ORDER_REF=" + ref)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (GateFailed, URLError, ValueError, TimeoutError) as exc:
        # Nunca imprimir exceção de request/urllib que possa conter headers/token.
        if isinstance(exc, GateFailed):
            print("SMOKE_BLOCKED: " + str(exc), file=sys.stderr)
        else:
            print("SMOKE_BLOCKED: falha de rede, entrada ou TLS; nenhum retry automático.",
                  file=sys.stderr)
        sys.exit(2)
