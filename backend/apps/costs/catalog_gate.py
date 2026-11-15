"""Commercial preflight: verify EVERY sellable Nuvemshop variant cost.

Published false is NOT synonymous with unsellable: 'unlisted' can be bought
via a direct URL. Stock does not affect cost eligibility. Neither local costs
nor a partial catalog page can establish complete coverage.
"""
from apps.catalog.client import read_products_page, CatalogReadError
from apps.costs.models import CostItem


class CatalogCostCoverageBlocked(ValueError):
    pass


def verify_active_catalog_costs(*, tenant, store_id, token, user_agent):
    """Fail closed if ANY visible/unlisted variant lacks a matching verified cost.

    Read all pages; 10,000 is an explicit upper bound, not silent truncation.
    A stale price/variant mapping cannot approve a different variant ID.
    """
    try:
        numeric_store_id = int(store_id)
    except (TypeError, ValueError):
        raise CatalogCostCoverageBlocked("ID da loja inválido") from None
    if numeric_store_id <= 0 or str(numeric_store_id) != str(store_id):
        raise CatalogCostCoverageBlocked("ID da loja inválido")

    mapped = {}
    for item in CostItem.objects.filter(tenant=tenant):
        if item.external_variant_id:
            mapped[item.external_variant_id] = item

    seen = set()
    counted = 0
    per_page = 15
    for page in range(1, 10001):
        try:
            products = read_products_page(
                store_id=numeric_store_id, access_token=token,
                user_agent=user_agent, page=page, per_page=per_page,
            )
        except (CatalogReadError, ValueError):
            raise CatalogCostCoverageBlocked("Catálogo remoto incompleto ou indisponível") from None
        if not isinstance(products, list) or len(products) > per_page:
            raise CatalogCostCoverageBlocked("Página do catálogo remoto inválida")
        for product in products:
            if not isinstance(product, dict):
                raise CatalogCostCoverageBlocked("Produto remoto inválido")
            visibility = product.get("visibility")
            if visibility == "hidden":
                continue
            if visibility not in ("visible", "unlisted"):
                # API without visibility cannot distinguish hidden from
                # buyable unlisted when published=False.
                if product.get("published") is True:
                    visibility = "visible"
                else:
                    raise CatalogCostCoverageBlocked("Visibilidade não comprovada")
            variants = product.get("variants")
            if not isinstance(variants, list) or not variants:
                raise CatalogCostCoverageBlocked("Produto vendável sem variantes conferíveis")
            for variant in variants:
                if not isinstance(variant, dict):
                    raise CatalogCostCoverageBlocked("Variante inválida")
                variant_id = str(variant.get("id") or "")
                sku = variant.get("sku")
                if (not variant_id.isdecimal() or not isinstance(sku, str)
                        or not sku.strip() or sku != sku.strip()):
                    raise CatalogCostCoverageBlocked("Variante vendável sem SKU e ID íntegros")
                if variant_id in seen:
                    raise CatalogCostCoverageBlocked("Variante duplicada na paginação")
                seen.add(variant_id)
                counted += 1
                item = mapped.get(variant_id)
                if (item is None or item.sku != sku
                        or item.verified_at is None or item.verified_by_id is None
                        or item.unit_cost_cents is None or item.unit_cost_cents <= 0
                        or item.selling_price_cents is None
                        or item.selling_price_cents <= 0):
                    raise CatalogCostCoverageBlocked(
                        "SKU ativo sem custo verificado (variante: " + variant_id + ")"
                    )
        if len(products) < per_page:
            if not counted:
                raise CatalogCostCoverageBlocked("Nenhuma variante vendável para conferência")
            return counted
    raise CatalogCostCoverageBlocked("Limite de paginação excedido: cobertura inconclusiva")
