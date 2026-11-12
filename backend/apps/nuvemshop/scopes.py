"""Capacidades efetivas do token OAuth da loja.

Permissões extras concedidas pelo lojista não habilitam funcionalidades.
A aplicação somente faz chamadas GET suportadas e auditadas. write_*
não é usado como autorização para executar alterações.
"""


def parse_scopes(value: str) -> frozenset[str]:
    if not isinstance(value, str):
        return frozenset()
    return frozenset(part.strip().lower() for part in value.split(",")
                     if part.strip())


def has_product_access(value: str, *, customer_preview_enabled: bool = False) -> bool:
    """write_products também inclui leitura, conforme documentação oficial."""
    scopes = parse_scopes(value)
    return bool({"read_products", "write_products"} & scopes)


def has_customer_access(value: str, *, customer_preview_enabled: bool) -> bool:
    if not customer_preview_enabled:
        return False
    scopes = parse_scopes(value)
    # Scopes de Customer e Product são independentes no OAuth oficial.
    return bool({"read_customers", "write_customers"} & scopes)


def allowed_scopes(value: str, *, customer_preview_enabled: bool) -> bool:
    """Aceita permissões concedidas além das usadas; nunca concede poderes de escrita."""
    return has_product_access(value, customer_preview_enabled=customer_preview_enabled)
