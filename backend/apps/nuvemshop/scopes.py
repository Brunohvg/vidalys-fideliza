"""Controle restritivo de permissões Nuvemshop.

`read_customers` somente se a funcionalidade for explicitamente habilitada
na homologação e autorizada no Portal de Parceiros. Nunca aceitar write_*.
"""


def parse_scopes(value: str) -> frozenset[str]:
    if not isinstance(value, str):
        return frozenset()
    return frozenset(part.strip() for part in value.split(",") if part.strip())


PRODUCT_SCOPES = frozenset({"read_products"})
CUSTOMER_PREVIEW_SCOPES = frozenset({"read_products", "read_customers"})


def allowed_scopes(value: str, *, customer_preview_enabled: bool) -> bool:
    scopes = parse_scopes(value)
    return scopes == PRODUCT_SCOPES or (
        customer_preview_enabled and scopes == CUSTOMER_PREVIEW_SCOPES
    )


def has_product_access(value: str, *, customer_preview_enabled: bool) -> bool:
    return allowed_scopes(value, customer_preview_enabled=customer_preview_enabled)


def has_customer_access(value: str, *, customer_preview_enabled: bool) -> bool:
    return customer_preview_enabled and parse_scopes(value) == CUSTOMER_PREVIEW_SCOPES
