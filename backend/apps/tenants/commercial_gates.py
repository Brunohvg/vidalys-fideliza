"""GO/NO-GO por tenant: nenhuma única flag é autorização suficiente.

Mesmo que um deploy marque as flags de forma indevida, a checagem verifica
triggers de banco, OAuth, catálogo de custos, PSP e enforcement de checkout.
"""
import hashlib
import json
from django.conf import settings
from django.db import connection
from apps.costs.models import CostItem
from apps.loyalty.models import LoyaltyRule
from apps.nuvemshop.models import NuvemshopInstallation
from apps.nuvemshop.scopes import parse_scopes
from apps.nuvemshop.order_readonly import read_orders_page
from apps.nuvemshop.security import config, decrypt_token
from apps.tenants.models import Tenant

REQUIRED_LEDGER_TABLES = (
    "points_pointlot", "points_pointevent", "points_pointentry",
    "wallets_cashbackevent", "wallets_cashbackentry",
    "wallets_cashbackoriginentry",
    "loyalty_financialevidence", "loyalty_paymentproofaudit",
)


class CommercialGateBlocked(ValueError):
    pass


def verify_pg_immutable_tables():
    if connection.vendor != "postgresql":
        raise CommercialGateBlocked("Go-Live exige PostgreSQL real.")
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, t.tgname, t.tgenabled
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND NOT t.tgisinternal
              AND (t.tgname LIKE 'points_%_immutable'
                  OR t.tgname LIKE 'wallets_%_immutable'
                  OR t.tgname LIKE 'loyalty_%_immutable')
        """)
        rows=cursor.fetchall()
    for table in REQUIRED_LEDGER_TABLES:
        if not any(x==table and name==table+"_immutable" and enabled in ("O","A")
                   for x,name,enabled in rows):
            raise CommercialGateBlocked("Trigger PostgreSQL de imutabilidade ausente.")


def commercial_readiness(*, tenant, check_live_get=True):
    if tenant.status != Tenant.Status.ACTIVE:
        raise CommercialGateBlocked("Loja não está ativa.")
    if not (settings.FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED
            and settings.FIDELIZA_POINTS_WRITES_ENABLED
            and settings.FIDELIZA_LEDGER_WRITES_ENABLED
            and settings.FIDELIZA_NUVEMSHOP_COUPON_OUTBOUND_ENABLED
            and settings.FIDELIZA_NUVEMSHOP_COUPON_REVOCATION_ENABLED
            and settings.FIDELIZA_NUVEMSHOP_ORDER_RECHECK_ENABLED
            and settings.FIDELIZA_NUVEMSHOP_ORDER_WEBHOOKS_ENABLED
            and settings.FIDELIZA_NUVEMSHOP_ORDERS_PREVIEW_ENABLED
            and getattr(settings, "FIDELIZA_PAYMENT_PROOF_STRICT_ORIGIN_ENABLED", False)
            and getattr(settings, "FIDELIZA_CHECKOUT_OWNER_ENFORCEMENT_VERIFIED", False)
            and getattr(settings, "FIDELIZA_PSP_PER_TENANT_CREDENTIALS_VERIFIED", False)
            and settings.FIDELIZA_PAYMENT_PROOF_ENABLED
            and "pagarme_v5" in settings.FIDELIZA_TRUSTED_PAYMENT_ADAPTERS):
        raise CommercialGateBlocked("Pagamento, cupons ou prevenção no checkout não homologados.")
    verify_pg_immutable_tables()
    if tenant.platform != "nuvemshop" or not tenant.external_store_id:
        raise CommercialGateBlocked("Ativação comercial Nuvemshop requer loja vinculada.")
    rule = LoyaltyRule.objects.filter(tenant=tenant, enabled=True).first()
    if not rule or not rule.budget_cents or not rule.minimum_margin_bps:
        raise CommercialGateBlocked("Margem mínima e orçamento do programa ausentes.")
    if not CostItem.objects.filter(tenant=tenant, verified_at__isnull=False).exists():
        raise CommercialGateBlocked("Nenhum custo por SKU verificado.")
    cfg = config()
    install = NuvemshopInstallation.objects.filter(
        tenant=tenant, store_id=tenant.external_store_id,
        client_id=cfg.client_id,
    ).first()
    if not install or not {"read_orders","write_coupons"} <= parse_scopes(install.scope):
        raise CommercialGateBlocked("OAuth Nuvemshop necessita reinstalação e escopos válidos.")
    if check_live_get:
        read_orders_page(
            store_id=install.store_id,
            access_token=decrypt_token(install.token_ciphertext, cfg.token_keys),
            user_agent=cfg.user_agent,
        )
    # Digest reproduzível sem imprimir segredo, identificador ou cliente.
    fingerprint = hashlib.sha256(json.dumps({
        "tenant": str(tenant.pk), "store_id": install.store_id,
        "rule": str(rule.pk), "version": rule.version,
        "db": "postgresql", "triggers": 8, "oauth_live_get": check_live_get,
        "checkout_preventive": True, "psp_account_tenant_bound": True,
    }, sort_keys=True).encode()).hexdigest()
    return fingerprint
