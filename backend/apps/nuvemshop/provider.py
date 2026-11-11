"""Troca OAuth: somente destino oficial, sem redirect de token nem segredos no log."""
import json
from django.conf import settings
from .scopes import allowed_scopes, parse_scopes
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

TOKEN_URL = "https://www.tiendanube.com/apps/authorize/token"


class OAuthExchangeError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def exchange_code(code: str, client_id: str, client_secret: str, *, opener=None):
    if not isinstance(code, str) or not 6 <= len(code) <= 1024:
        raise OAuthExchangeError("Código de autorização inválido.")
    payload = json.dumps({
        "client_id": client_id, "client_secret": client_secret,
        "grant_type": "authorization_code", "code": code,
    }).encode("utf-8")
    req = Request(
        TOKEN_URL, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    transport = opener or build_opener(_NoRedirect())
    try:
        with transport.open(req, timeout=8) as response:
            body = response.read(32769)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise OAuthExchangeError("Falha na autorização com a Nuvemshop.") from None
    if len(body) > 32768:
        raise OAuthExchangeError("Resposta OAuth acima do limite.")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise OAuthExchangeError("Resposta OAuth inválida.") from None
    if not isinstance(data, dict):
        raise OAuthExchangeError("Resposta OAuth inválida.")
    token = data.get("access_token")
    user_id = data.get("user_id") or data.get("store_id")
    scopes = data.get("scope")
    token_type = str(data.get("token_type", "")).lower()
    if not isinstance(token, str) or not 16 <= len(token) <= 4096:
        raise OAuthExchangeError("Token OAuth inválido.")
    if (isinstance(user_id, bool) or len(str(user_id)) > 20 or
            not str(user_id).isascii() or not str(user_id).isdecimal() or int(user_id) <= 0):
        raise OAuthExchangeError("Loja OAuth inválida.")
    if not isinstance(scopes, str):
        raise OAuthExchangeError("Escopos OAuth inválidos.")
    # Nunca armazenar credencial com poderes de escrita sem aprovação do escopo.
    if not allowed_scopes(scopes, customer_preview_enabled=(
            settings.FIDELIZA_NUVEMSHOP_CUSTOMERS_PREVIEW_ENABLED)) or token_type != "bearer":
        raise OAuthExchangeError("Permissões inesperadas; somente leituras aprovadas são permitidas.")
    if data.get("user_id") is not None and data.get("store_id") is not None:
        if str(data["user_id"]) != str(data["store_id"]):
            raise OAuthExchangeError("Loja OAuth inconsistente.")
    return {"access_token": token, "store_id": str(int(user_id)),
            "scope": ",".join(sorted(parse_scopes(scopes)))}
