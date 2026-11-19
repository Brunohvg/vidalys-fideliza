"""Endereço público do clube (/clube/<endereço>).

O lojista escolhe um endereço curto. O anterior vira apelido, para que
links e e-mails já enviados continuem abrindo a mesma loja.
"""
import re
import uuid

from django.utils.text import slugify

ADDRESS = re.compile(r"^[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){2,39}$")
RESERVED = frozenset({
    "admin", "api", "app", "clube", "clubes", "conhecer", "demo", "entrar", "sair",
    "cadastrar", "confirmar", "confirmar-conta", "redefinir-senha", "esqueci-senha",
    "participar", "retirar", "static", "media", "assets", "suporte", "ajuda",
    "vidalys", "fideliza", "nuvemshop", "login", "logout", "www",
})


def normalize_address(raw):
    if not isinstance(raw, str):
        raise ValueError("Endereço inválido.")
    value = slugify(raw.strip())[:40].strip("-")
    if not ADDRESS.match(value):
        raise ValueError("Use de 3 a 40 letras, números ou hífens, sem acento.")
    if value in RESERVED:
        raise ValueError("Este endereço é reservado. Escolha outro.")
    return value


def address_taken(value, *, tenant_id=None):
    from .models import Tenant, TenantSlugAlias
    if Tenant.objects.filter(slug=value).exclude(pk=tenant_id).exists():
        return True
    return TenantSlugAlias.objects.filter(slug=value).exclude(tenant_id=tenant_id).exists()


def first_free_address(name):
    """Endereço limpo para loja nova: nome da loja, com número só se repetir."""
    base = slugify(name or "")[:34].strip("-")
    if len(base) < 3 or base in RESERVED:
        base = "loja-" + (base or "clube")
        base = base[:34].strip("-")
    for number in range(1, 50):
        candidate = base if number == 1 else f"{base}-{number}"
        if not address_taken(candidate):
            return candidate
    return f"{base}-{uuid.uuid4().hex[:6]}"


def canonical_slug(slug):
    """Endereço atual da loja; apelidos antigos apontam para o novo."""
    from .models import Tenant, TenantSlugAlias
    if not isinstance(slug, str) or Tenant.objects.filter(slug=slug).exists():
        return slug
    alias = TenantSlugAlias.objects.filter(slug=slug).select_related("tenant").first()
    return alias.tenant.slug if alias else slug
