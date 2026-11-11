"""Chaves no secret manager, nunca nos campos da API ou no repositório."""
import hashlib
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, MultiFernet, InvalidToken


CALLBACK_PATH = "/api/v1/oauth/nuvemshop/callback/"
AUTHORIZE_HOST = "https://www.tiendanube.com"


class OAuthConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    client_secret: str
    callback_url: str
    user_agent: str
    token_keys: str


def config():
    env = os.environ
    client_id = env.get("NUVEMSHOP_CLIENT_ID", "").strip()
    client_secret = env.get("NUVEMSHOP_CLIENT_SECRET", "").strip()
    callback = env.get("NUVEMSHOP_OAUTH_CALLBACK_URL", "").strip()
    user_agent = env.get("NUVEMSHOP_API_USER_AGENT", "").strip()
    keys = env.get("NUVEMSHOP_TOKEN_KEYS", "").strip()
    parsed = urlsplit(callback)
    if not (client_id.isascii() and client_id.isdecimal() and int(client_id) > 0
            and client_secret and 4 <= len(user_agent) <= 150
            and parsed.scheme == "https" and parsed.netloc and not parsed.username
            and not parsed.password and parsed.path == CALLBACK_PATH
            and not parsed.query and not parsed.fragment and keys):
        raise OAuthConfigurationError("Integração indisponível: configuração incompleta.")
    try:
        _cipher(keys)
    except (ValueError, TypeError) as exc:
        raise OAuthConfigurationError("Chave de criptografia inválida.") from None
    return OAuthConfig(client_id, client_secret, callback, user_agent, keys)


def _cipher(keys):
    return MultiFernet([Fernet(part.strip().encode("ascii"))
                        for part in keys.split(",") if part.strip()])


def encrypt_token(token: str, keys: str):
    return _cipher(keys).encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str, keys: str):
    try:
        return _cipher(keys).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError):
        raise OAuthConfigurationError("Token não pode ser decifrado; revise as chaves.") from None


def digest(value: str):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
