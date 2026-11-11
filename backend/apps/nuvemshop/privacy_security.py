"""Identificadores irreversíveis para solicitações de privacidade.

A chave é o segredo do aplicativo Nuvemshop, já isolado no backend.
Rotação do segredo exige estratégia de reindexação dos pedidos pendentes.
"""
import hashlib
import hmac


def email_identity_digest(value: object, secret: str) -> str:
    if not isinstance(value, str) or not secret:
        return ""
    email = value.strip().casefold()
    if (not 3 <= len(email) <= 254 or email.count("@") != 1
            or any(ord(char) < 33 or ord(char) == 127 for char in email)):
        return ""
    return hmac.new(
        secret.encode("utf-8"),
        ("fideliza:privacy-email:v1:" + email).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def privacy_event_key(topic: str, store_id: str, customer_id: str,
                      request_id: str, secret: str) -> str:
    canonical = f"fideliza:privacy-event:v2:{topic}:{store_id}:{customer_id}:{request_id}"
    return hmac.new(secret.encode("utf-8"), canonical.encode("ascii"),
                    hashlib.sha256).hexdigest()


def legacy_event_key(topic: str, store_id: str, customer_id: str,
                     request_id: str) -> str:
    # Reconhecer eventos emitidos antes da migração para HMAC, sem duplicar.
    canonical = f"nuvemshop-privacy-v1:{topic}:{store_id}:{customer_id}:{request_id}"
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
