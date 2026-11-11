"""Cliente interno HTTP de leitura Admin API Nuvemshop 2025-03.

NÃO expõe endpoint para enviar token, NÃO armazena segredos, NÃO consulta
nenhuma loja até que OAuth server-side esteja aprovado e implantado.
"""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


API_ROOT = "https://api.tiendanube.com/2025-03"


class CatalogReadError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Nunca transportar Bearer token por redirecionamentos externos.
        return None


def read_products_page(*, store_id: int, access_token: str,
                       user_agent: str, page: int = 1, per_page: int = 15,
                       opener=None, pause=time.sleep):
    if isinstance(store_id, bool) or not isinstance(store_id, int) or store_id < 1:
        raise ValueError("store_id inválido")
    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError("Token obrigatório no servidor")
    if not isinstance(user_agent, str) or not (4 <= len(user_agent.strip()) <= 150):
        raise ValueError("User-Agent do aplicativo é obrigatório")
    if not (isinstance(page, int) and not isinstance(page, bool) and 1 <= page <= 10000):
        raise ValueError("Página fora dos limites")
    if not (isinstance(per_page, int) and not isinstance(per_page, bool) and 1 <= per_page <= 15):
        raise ValueError("Prévia limitada a 15 produtos por página")

    transport = opener or build_opener(_NoRedirect())
    query = urlencode({"page": page, "per_page": per_page})
    request = Request(
        f"{API_ROOT}/{store_id}/products?{query}",
        headers={"Authorization": f"Bearer {access_token}",
                 "User-Agent": user_agent,
                 "Accept": "application/json"},
        method="GET",
    )
    for attempt in range(3):
        try:
            with transport.open(request, timeout=8) as response:
                content = response.read(2_000_001)
                if len(content) > 2_000_000:
                    raise CatalogReadError("Resposta da Nuvemshop acima do limite de 2 MB.")
                data = json.loads(content)
                if not isinstance(data, list):
                    raise CatalogReadError("Resposta inesperada da Nuvemshop.")
                return data
        except HTTPError as exc:
            # Não incluir URL, body ou headers na mensagem (podem conter segredos).
            if exc.code in (429, 502, 503, 504) and attempt < 2:
                pause(min(2, attempt + 1))
                continue
            raise CatalogReadError(f"Nuvemshop indisponível (HTTP {exc.code}).") from None
        except (URLError, TimeoutError, OSError) as exc:
            if attempt < 2:
                pause(min(2, attempt + 1))
                continue
            raise CatalogReadError("Falha de comunicação com a Nuvemshop.") from None
        except (UnicodeError, json.JSONDecodeError):
            raise CatalogReadError("JSON inválido recebido da Nuvemshop.") from None
    raise CatalogReadError("Limite de tentativas de leitura atingido.")
