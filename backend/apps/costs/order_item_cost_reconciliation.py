"""Deterministic order-item COGS reconciliation from a live OAuth GET.

No HTTP payload, merchant-provided SKU list, catalog price or checkout form
may bypass the read_order source boundary. Simulations are not settlement.
"""
from dataclasses import dataclass, replace
import hmac
from django.conf import settings
from django.utils.crypto import salted_hmac
from decimal import Decimal, InvalidOperation
import hashlib
import json

from apps.costs.models import CostItem
from apps.loyalty.services import OrderCosts
from apps.nuvemshop.order_readonly import read_order, safe_id, OrderReadError, COST_FIELDS
from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.scopes import parse_scopes
from apps.nuvemshop.security import config, decrypt_token


class OrderItemCostBlocked(ValueError):
    pass


@dataclass(frozen=True)
class ReconciledOrderCosts:
    costs: OrderCosts
    gross_subtotal_cents: int
    discounts_cents: int
    eligible_net_cents: int
    shipping_owner_cents: int
    shipping_customer_cents: int
    shipping_subsidy_cents: int
    cogs_cents: int
    contribution_before_rewards_cents: int
    sale_total_cents: int
    snapshot_digest: str
    order_id: str = ""
    tenant_id: str = ""
    cost_versions: tuple = ()
    verified_signature: str = ""


def _money(value, label):
    if isinstance(value, bool) or value is None:
        raise OrderItemCostBlocked(label + ": valor ausente")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise OrderItemCostBlocked(label + ": valor inválido") from None
    pennies = amount * 100
    if (not amount.is_finite() or amount < 0
            or pennies != pennies.to_integral_value()
            or pennies > 1_000_000_000):
        raise OrderItemCostBlocked(label + ": centavos fora do limite")
    return int(pennies)


def _id(value, field):
    identity = safe_id(value)
    if identity is None:
        raise OrderItemCostBlocked(field + ": identificador ausente ou inválido")
    return identity


def reconcile_order_item_costs(*, order, tenant, expected_order_id,
                               expected_total_cents, payment_fee_cents=0):
    """Only call with an authenticated and ID-checked Nuvemshop order snapshot.

    This function enforces completeness; provider authentication belongs to
    read_verified_nuvemshop_order_costs. Returned quote is calculation only.
    """
    if (not isinstance(order, dict) or
            _id(order.get("id"), "order_id") != _id(expected_order_id, "order_id")
            or (order.get("store_id") is not None
                and _id(order.get("store_id"), "store_id") !=
                _id(tenant.external_store_id, "store_id"))
            or order.get("currency") != "BRL"
            or order.get("payment_status") != "paid"
            or order.get("status") == "cancelled"):
        raise OrderItemCostBlocked("Pedido/loja/moeda ou estado não autenticável")
    if type(expected_total_cents) is not int or expected_total_cents <= 0:
        raise OrderItemCostBlocked("Valor de venda inválido")
    if type(payment_fee_cents) is not int or not 0 <= payment_fee_cents <= 1_000_000_000:
        raise OrderItemCostBlocked("Tarifa PSP não verificada")
    products = order.get("products")
    if not isinstance(products, list) or not 0 < len(products) <= 300:
        raise OrderItemCostBlocked("Pedido sem 100% das linhas conferíveis")

    variants = []
    versions = []
    unique_lines = set()
    subtotal = cogs = 0
    for line in products:
        if not isinstance(line, dict):
            raise OrderItemCostBlocked("Linha de produto malformada")
        line_id = _id(line.get("id"), "line_id")
        product_id = _id(line.get("product_id"), "product_id")
        variant_id = _id(line.get("variant_id"), "variant_id")
        sku = line.get("sku")
        qty = line.get("quantity")
        if isinstance(qty, str) and qty.isascii() and qty.isdecimal():
            qty = int(qty)
        if (line_id in unique_lines or type(qty) is not int
                or not 1 <= qty <= 10000 or not isinstance(sku, str)
                or not sku.strip() or sku != sku.strip()):
            raise OrderItemCostBlocked("Linha duplicada, quantidade ou SKU inválido")
        unique_lines.add(line_id)
        price = _money(line.get("price"), "preço por linha")
        if price <= 0:
            raise OrderItemCostBlocked("Preço unitário não positivo")
        items = list(CostItem.objects.filter(
            tenant=tenant, external_variant_id=variant_id,
        ))
        if (len(items) != 1 or items[0].sku != sku
                or items[0].verified_at is None or items[0].verified_by_id is None
                or type(items[0].unit_cost_cents) is not int
                or items[0].unit_cost_cents <= 0):
            raise OrderItemCostBlocked(
                "Custo verificado ausente ou SKU/variante divergente: " + variant_id
            )
        item = items[0]
        variants.append((item.pk, qty))
        versions.append((str(item.pk), item.version))
        subtotal += price * qty
        cogs += item.unit_cost_cents * qty
        if max(cogs, subtotal) > 1_000_000_000:
            raise OrderItemCostBlocked("Subtotal ultrapassa limite")

    declared_subtotal = _money(order.get("subtotal"), "subtotal")
    discount = _money(order.get("discount"), "desconto total")
    coupon_discount = _money(order.get("discount_coupon", "0.00"), "desconto cupom")
    owner_shipping = _money(order.get("shipping_cost_owner"), "frete do lojista")
    customer_shipping = _money(order.get("shipping_cost_customer"), "frete do cliente")
    total = _money(order.get("total"), "total do pedido")
    if (subtotal != declared_subtotal or discount > subtotal
            or coupon_discount > discount or
            subtotal - discount + customer_shipping != total or
            total != expected_total_cents):
        raise OrderItemCostBlocked(
            "Subtotal, desconto, frete ou total divergem da venda PSP"
        )
    eligible = subtotal - discount
    if eligible <= 0:
        raise OrderItemCostBlocked("Subtotal elegível líquido inexistente")
    subsidy = max(owner_shipping - customer_shipping, 0)
    contribution = eligible - cogs - subsidy - payment_fee_cents
    fingerprint = hashlib.sha256(json.dumps({
        "tenant":str(tenant.pk), "store":str(tenant.external_store_id),
        "order":str(expected_order_id), "lines":[[str(i),q] for i,q in variants],
        "cost_versions": versions,
        "subtotal":subtotal, "discount":discount, "owner_shipping":owner_shipping,
        "customer_shipping":customer_shipping,"cogs":cogs,"psp_fees":payment_fee_cents,
        "total":total,
    }, sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return ReconciledOrderCosts(
        costs=OrderCosts(lines=tuple(variants),
            payment_fee_cents=payment_fee_cents,
            shipping_subsidy_cents=subsidy),
        gross_subtotal_cents=subtotal, discounts_cents=discount,
        eligible_net_cents=eligible, shipping_owner_cents=owner_shipping,
        shipping_customer_cents=customer_shipping,
        shipping_subsidy_cents=subsidy, cogs_cents=cogs,
        contribution_before_rewards_cents=contribution,
        sale_total_cents=total, snapshot_digest=fingerprint,
        order_id=str(expected_order_id), tenant_id=str(tenant.pk),
        cost_versions=tuple(versions),
    )


def _signature(sale, quote):
    # Bind EVERY financial field and the exact quantity/cost mapping; signing
    # only the snapshot hash would let an in-process caller replace fields.
    payload = json.dumps([
        str(sale.tenant_id), str(sale.pk), quote.snapshot_digest,
        quote.order_id, quote.tenant_id, quote.sale_total_cents,
        quote.gross_subtotal_cents, quote.discounts_cents,
        quote.eligible_net_cents, quote.shipping_owner_cents,
        quote.shipping_customer_cents, quote.shipping_subsidy_cents,
        quote.cogs_cents, quote.contribution_before_rewards_cents,
        [[str(pk), qty] for pk, qty in quote.costs.lines],
        quote.costs.payment_fee_cents, quote.costs.shipping_subsidy_cents,
        quote.costs.other_variable_costs_cents,
        list(quote.cost_versions),
    ], separators=(",", ":"), ensure_ascii=True)
    return salted_hmac(
        "vidalys.oauth-order-cost-quote.v2", payload,
        secret=settings.SECRET_KEY, algorithm="sha256",
    ).hexdigest()


def verify_verified_quote(*, sale, quote):
    """Fail closed even if an internal caller supplies arbitrary OrderCosts."""
    if (not isinstance(quote, ReconciledOrderCosts)
            or quote.order_id != sale.external_reference
            or quote.tenant_id != str(sale.tenant_id)
            or quote.sale_total_cents != sale.reported_total_cents
            or quote.eligible_net_cents !=
               quote.gross_subtotal_cents - quote.discounts_cents
            or quote.shipping_subsidy_cents !=
               max(quote.shipping_owner_cents - quote.shipping_customer_cents, 0)
            or quote.contribution_before_rewards_cents !=
               quote.eligible_net_cents - quote.cogs_cents
               - quote.shipping_subsidy_cents - quote.costs.payment_fee_cents
               - quote.costs.other_variable_costs_cents
            or quote.costs.shipping_subsidy_cents != quote.shipping_subsidy_cents
            or not quote.verified_signature
            or not hmac.compare_digest(quote.verified_signature,
                                       _signature(sale,quote))):
        raise OrderItemCostBlocked("Cotação de custos sem prova OAuth")
    identifiers = [pk for pk, _ in quote.cost_versions]
    actual = list(CostItem.objects.select_for_update().filter(
        tenant_id=sale.tenant_id,pk__in=identifiers))
    current = {str(item.pk):item for item in actual}
    if (len(actual) != len(identifiers)
            or len(set(identifiers)) != len(identifiers)):
        raise OrderItemCostBlocked("Linhas de custo alteradas")
    cost_sum = 0
    for pk, version in quote.cost_versions:
        item = current.get(pk)
        if (item is None or item.version != version or not item.verified_at
                or item.verified_by_id is None or not item.unit_cost_cents):
            raise OrderItemCostBlocked("Custo por variante perdeu verificação")
    for pk, quantity in quote.costs.lines:
        cost_sum += current[str(pk)].unit_cost_cents * quantity
    if cost_sum != quote.cogs_cents:
        raise OrderItemCostBlocked("Custo unitário mudou após consulta OAuth")
    return quote


def read_verified_nuvemshop_order_costs(*, sale, payment_fee_cents, opener=None):
    """Fixed-origin OAuth GET; never accept an untrusted caller's order JSON."""
    if sale.channel != "nuvemshop":
        raise OrderItemCostBlocked("Canal não possui snapshot OAuth de pedido")
    tenant = sale.tenant
    cfg = config()
    installation = NuvemshopInstallation.objects.filter(
        tenant=tenant, store_id=tenant.external_store_id,
        client_id=cfg.client_id,
    ).first()
    if installation is None or "read_orders" not in parse_scopes(installation.scope):
        raise OrderItemCostBlocked("Instalação OAuth read_orders indisponível")
    try:
        order = read_order(
            store_id=installation.store_id, order_id=sale.external_reference,
            access_token=decrypt_token(installation.token_ciphertext,cfg.token_keys),
            user_agent=cfg.user_agent, fields=COST_FIELDS, opener=opener,
        )
    except (OrderReadError, ValueError):
        raise OrderItemCostBlocked("GET OAuth de linhas do pedido indisponível") from None
    quote = reconcile_order_item_costs(
        order=order, tenant=tenant, expected_order_id=sale.external_reference,
        expected_total_cents=sale.reported_total_cents,
        payment_fee_cents=payment_fee_cents,
    )
    return replace(quote, verified_signature=_signature(sale, quote))
