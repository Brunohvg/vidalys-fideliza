"""Leitura mínima de clientes Nuvemshop 2025-03 apenas para prévia de vínculo.

Não grava clientes e não retorna a resposta bruta ao browser. Usar somente
tokens OAuth com read_customers do mesmo tenant e e-mails já confirmados.
"""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from apps.catalog.client import API_ROOT


class CustomerReadError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_customer_candidates(*, store_id: int, access_token: str, user_agent: str,
                             email: str, opener=None, pause=time.sleep):
    if isinstance(store_id, bool) or not isinstance(store_id, int) or not 0 < store_id:
        raise ValueError("ID da loja inválido.")
    if not isinstance(access_token, str) or len(access_token) < 16:
        raise ValueError("Token ausente.")
    if not isinstance(user_agent, str) or not 4 <= len(user_agent.strip()) <= 150:
        raise ValueError("User-Agent inválido.")
    if (not isinstance(email, str) or len(email) > 254
            or "@" not in email or any(c in email for c in "\r\n\x00")):
        raise ValueError("E-mail inválido.")

    # Pesquisa filtrada em vez de baixar o catálogo inteiro de clientes.
    params = urlencode({"email": email, "fields": "id,email", "per_page": 10, "page": 1})
    request = Request(
        f"{API_ROOT}/{store_id}/customers?{params}",
        method="GET",
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": user_agent,
                 "Accept": "application/json"},
    )
    transport = opener or build_opener(_NoRedirect())
    for attempt in range(3):
        try:
            with transport.open(request, timeout=8) as response:
                content = response.read(65537)
                if len(content) > 65536:
                    raise CustomerReadError("Resposta acima do limite.")
                data = json.loads(content)
                if not isinstance(data, list) or len(data) > 10:
                    raise CustomerReadError("Resposta inesperada da Nuvemshop.")
                # Evitar retornar dados pessoais extras acidentalmente.
                return [{
                    "id": str(item["id"]), "email": item["email"].strip().casefold()
                } for item in data
                    if isinstance(item, dict)
                    and isinstance(item.get("id"), int) and not isinstance(item["id"], bool)
                    and item["id"] > 0 and isinstance(item.get("email"), str)
                    and len(item["email"]) <= 254]
        except HTTPError as exc:
            if exc.code in (429, 502, 503, 504) and attempt < 2:
                pause(min(2, attempt + 1))
                continue
            raise CustomerReadError(f"Consulta indisponível (HTTP {exc.code}).") from None
        except (URLError, TimeoutError, OSError):
            if attempt < 2:
                pause(min(2, attempt + 1))
                continue
            raise CustomerReadError("Falha temporária na Nuvemshop.") from None
        except (UnicodeError, json.JSONDecodeError, KeyError, AttributeError):
            raise CustomerReadError("Resposta inesperada da Nuvemshop.") from None
    raise CustomerReadError("Limite de tentativas alcançado.")


def exact_email_match(candidates: list[dict], email: str):
    """Se houver mais de uma conta para o mesmo endereço, nunca assumir uma."""
    normalized = email.strip().casefold()
    matches = sorted({row["id"] for row in candidates if row["email"] == normalized})
    if len(candidates) >= 10 or len(matches) > 1:
        return "ambiguous", None
    if len(matches) == 1:
        return "one_exact_match", matches[0]
    return "not_found", None
