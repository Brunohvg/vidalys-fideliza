"""Prévia pura de conciliação de variantes Nuvemshop com custos locais.

Nenhuma gravação, autorização de desconto ou remapeamento automático. IDs
são a chave primária de conciliação; SKU/EAN só ajudam na revisão humana.
"""

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

MAX_PRODUCTS = 15
MAX_VARIANTS = 50
MAX_SNAPSHOT_BYTES = 150_000


class InvalidSnapshot(ValueError):
    """Amostra fora do contrato de prévia de catálogo."""


def _id(value):
    if isinstance(value, bool):
        raise InvalidSnapshot("IDs de produto e variante devem ser numéricos.")
    value = str(value).strip()
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise InvalidSnapshot("IDs de produto e variante devem ser numéricos positivos.")
    return str(int(value))


def _label(value):
    if isinstance(value, dict):
        value = value.get("pt") or value.get("es") or value.get("en") or next(
            (v for v in value.values() if isinstance(v, str) and v.strip()), ""
        )
    if not isinstance(value, str) or not value.strip():
        raise InvalidSnapshot("Produto sem nome válido.")
    return value.strip()[:180]


def _sku(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidSnapshot("SKU precisa ser texto, sem conversão de números.")
    result = value.strip()
    if len(result) > 100:
        raise InvalidSnapshot("SKU acima do limite de 100 caracteres.")
    return result.upper()


def _barcode(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidSnapshot("EAN/código de barras precisa ser texto.")
    result = value.strip()
    if len(result) > 80:
        raise InvalidSnapshot("Código de barras acima do limite de 80 caracteres.")
    return result


def _money(value, field, required=False):
    if value is None or value == "":
        if required:
            return None  # Produtos sob consulta podem não ter preço.
        return None
    # Não aceitar float: números como 19.9 podem perder informação na conversão.
    if isinstance(value, bool) or isinstance(value, (float, dict, list)):
        raise InvalidSnapshot(f"{field}: use decimal em texto.")
    if not isinstance(value, (int, str)):
        raise InvalidSnapshot(f"{field}: formato inválido.")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        raise InvalidSnapshot(f"{field}: valor monetário inválido.") from None
    if not parsed.is_finite() or parsed <= 0 or parsed > 10_000_000:
        raise InvalidSnapshot(f"{field}: valor deve ser positivo e finito.")
    cents = parsed * 100
    if cents != cents.to_integral_value():
        raise InvalidSnapshot(f"{field}: máximo de duas casas decimais.")
    return int(cents)


def normalize_products(products):
    if not isinstance(products, list) or not (1 <= len(products) <= MAX_PRODUCTS):
        raise InvalidSnapshot(f"Informe de 1 a {MAX_PRODUCTS} produtos para a amostra.")
    normalized = []
    for p in products:
        if not isinstance(p, dict):
            raise InvalidSnapshot("Cada produto deve ser um objeto JSON.")
        product_id = _id(p.get("id"))
        name = _label(p.get("name"))
        variants = p.get("variants")
        if not isinstance(variants, list) or not variants:
            raise InvalidSnapshot("Cada produto precisa incluir pelo menos uma variante.")
        for v in variants:
            if not isinstance(v, dict):
                raise InvalidSnapshot("Cada variante deve ser um objeto JSON.")
            variant_id = _id(v.get("id"))
            if "product_id" in v and v["product_id"] is not None and _id(v["product_id"]) != product_id:
                raise InvalidSnapshot("ID do produto diverge do ID da variante.")
            normalized.append({
                "product_id": product_id, "product_name": name,
                "variant_id": variant_id,
                "sku": _sku(v.get("sku")),
                "barcode": _barcode(v.get("barcode")),
                "price_cents": _money(v.get("price"), "Preço", required=True),
                "promotional_price_cents": _money(v.get("promotional_price"), "Preço promocional"),
                "api_cost_cents": _money(v.get("cost"), "Custo da API"),
            })
            if len(normalized) > MAX_VARIANTS:
                raise InvalidSnapshot(f"Máximo de {MAX_VARIANTS} variantes por amostra.")
    return normalized


def reconcile_products(products, local_items):
    """Compara somente memória; local_items é um queryset já filtrado por tenant."""
    rows = normalize_products(products)
    local_by_id = {
        str(x.external_variant_id): x
        for x in local_items if x.external_variant_id
    }
    local_by_sku = defaultdict(list)
    for item in local_items:
        if item.sku:
            local_by_sku[item.sku.strip().upper()].append(item)

    ids = Counter(x["variant_id"] for x in rows)
    skus = Counter(x["sku"] for x in rows if x["sku"])
    out = []
    counts = {"matched": 0, "review_required": 0, "unmapped": 0,
              "missing_api_cost": 0, "missing_sku": 0}
    for r in rows:
        remote_id = r["variant_id"]
        sku = r["sku"]
        local = local_by_id.get(remote_id)
        issue_codes = []
        match_type = "none"
        if ids[remote_id] > 1:
            issue_codes.append("duplicate_variant_id")
        if not sku:
            counts["missing_sku"] += 1
        elif skus[sku] > 1:
            issue_codes.append("duplicate_sku_in_sample")
        if r["api_cost_cents"] is None:
            counts["missing_api_cost"] += 1

        if local is not None:
            match_type = "variant_id"
            if sku and local.sku and sku != local.sku.strip().upper():
                issue_codes.append("sku_changed")
            if local.unit_cost_cents is not None and r["api_cost_cents"] is not None:
                if local.unit_cost_cents != r["api_cost_cents"]:
                    issue_codes.append("cost_differs_from_local")
            if local.selling_price_cents is not None and r["price_cents"] is not None:
                if local.selling_price_cents != r["price_cents"]:
                    issue_codes.append("price_differs_from_local")
            if local.verified_at is None:
                issue_codes.append("local_cost_not_reviewed")
        elif sku:
            candidates = local_by_sku[sku]
            if len(candidates) > 1:
                issue_codes.append("ambiguous_local_sku")
            elif len(candidates) == 1:
                local = candidates[0]
                match_type = "sku_candidate"
                if local.external_variant_id and local.external_variant_id != remote_id:
                    issue_codes.append("variant_id_changed")
                else:
                    issue_codes.append("confirm_sku_mapping")

        if match_type == "variant_id":
            decision = "review_required" if issue_codes else "matched"
        elif local is not None:
            decision = "review_required"
        else:
            decision = "unmapped" if not issue_codes else "review_required"

        counts[decision] += 1
        out.append({
            **r,
            "decision": decision,
            "match_type": match_type,
            "local_item_id": str(local.pk) if local else None,
            "local_reference": local.reference if local else None,
            "local_cost_cents": local.unit_cost_cents if local else None,
            "local_verified": bool(local and local.verified_at),
            "issues": issue_codes,
            "will_modify_cost": False,
            "will_modify_product": False,
        })

    return {
        "mode": "read_only_snapshot_preview",
        "source": "operator_supplied_json",
        "automatically_approved": False,
        "writes_performed": 0,
        "summary": {"products": len(products), "variants": len(out), **counts},
        "items": out,
        "warnings": [
            "Amostra JSON fornecida pelo operador; não foi obtida da API em tempo real.",
            "Não há importação, atualização de custos, ligação de variantes ou publicação automática.",
            "SKU e código de barras não substituem o ID confirmado da variante.",
            "Custos da Nuvemshop podem estar ausentes; custos locais conferidos permanecem intactos.",
        ],
    }
