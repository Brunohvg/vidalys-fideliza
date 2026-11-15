#!/usr/bin/env python3
"""PR24: checagem read-only no PostgreSQL REAL dos eventos HTTP do tenant QA.

Fases:
  pre  -> garante tenant independente e contato previamente verificado.
  post -> verifica pedido informado, inbox e ausência de crédito financeiro.
Nunca cria clientes, altera banco, salva token ou imprime telefone/e-mail.
"""
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


class GateFailed(RuntimeError):
    pass


def required(name):
    value = os.getenv(name, "")
    if not value:
        raise GateFailed(f"Falta {name}")
    return value


def ensure(ok, message):
    if not ok:
        raise GateFailed(message)


def main():
    ensure(os.getenv("FIDELIZA_ENVIRONMENT") == "homolog", "Somente homologação")
    ensure(len(sys.argv) == 2 and sys.argv[1] in {"pre", "post"},
           "Uso: python scripts/homolog_smoke_db_audit.py pre|post")
    stage = sys.argv[1]
    expected_db = required("FIDELIZA_EXPECTED_DATABASE")
    expected_host = required("FIDELIZA_EXPECTED_PG_HOST")
    require_tenant = uuid.UUID(required("FIDELIZA_SMOKE_TENANT_ID"))
    slug = required("FIDELIZA_SMOKE_CLUB_SLUG")
    phone = required("FIDELIZA_SMOKE_PHONE_E164")
    ensure(bool(re.fullmatch(r"(?:qa|homolog)-[a-z0-9-]{3,52}", slug)),
           "O slug precisa identificar loja QA isolada")
    ensure(bool(re.fullmatch(r"\+[1-9]\d{7,14}", phone)),
           "Contato QA inválido: E.164 obrigatório")

    import django
    django.setup()

    from django.conf import settings
    from django.db import connection
    from apps.tenants.models import Tenant
    from apps.customers.services import find_verified_customer
    from apps.sales.models import SaleRecord, SaleEventReceipt
    from apps.loyalty.models import LoyaltyGrant, LoyaltyVoucher, FinancialEvidence
    from apps.points.models import PointWallet, PointLot
    from apps.wallets.models import CashbackWallet

    ensure(connection.vendor == "postgresql", "A conexão não é PostgreSQL")
    ensure(connection.settings_dict["HOST"] == expected_host, "Host não autorizado")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        ensure(cursor.fetchone()[0] == expected_db, "Banco não é a homologação esperada")

    tenant = Tenant.objects.filter(pk=require_tenant, slug=slug,
                                   status=Tenant.Status.ACTIVE,
                                   platform="independent",
                                   external_store_id__isnull=True).first()
    ensure(tenant is not None, "Tenant QA isolado não encontrado")
    ensure("bibel" not in tenant.name.casefold(), "Tenant não pode representar Bibelô")
    profile = find_verified_customer(tenant_id=tenant.pk, phone_e164=phone)
    ensure(profile is not None and profile.participant_id is not None,
           "Contato WhatsApp QA precisa estar previamente comprovado")
    ensure(profile.participant.status == "active", "Participante QA não está ativo")

    for flag in ("FIDELIZA_POINTS_WRITES_ENABLED",
                 "FIDELIZA_LEDGER_WRITES_ENABLED",
                 "FIDELIZA_LOYALTY_FINANCIAL_EXECUTION_ENABLED"):
        ensure(getattr(settings, flag, False) is False,
               f"Flag financeira ligada: {flag}")
    ensure(not getattr(settings, "FIDELIZA_TRUSTED_PAYMENT_ADAPTERS", frozenset()),
           "Adapter PSP financeiro deve permanecer OFF")

    ensure(not LoyaltyGrant.objects.filter(tenant=tenant).exists(), "QA já contém grants")
    ensure(not LoyaltyVoucher.objects.filter(tenant=tenant).exists(), "QA já contém vouchers")
    ensure(not PointWallet.objects.filter(tenant=tenant).exists(), "QA já contém pontos")
    ensure(not CashbackWallet.objects.filter(tenant=tenant).exists(), "QA já contém cashback")
    if stage == "pre":
        ensure(not SaleRecord.objects.filter(tenant=tenant).exists(),
               "O tenant de teste precisa estar sem pedidos antes do smoke")
        print("QA_TENANT_PREFLIGHT_OK tenant_isolated=YES verified_contact=YES "
              "financial_flags=OFF baseline_empty=YES")
        return

    ref = required("FIDELIZA_SMOKE_ORDER_REF")
    ensure(bool(re.fullmatch(r"PR24-[A-F0-9]{20}", ref)),
           "Referência gerada pelo smoke HTTP é obrigatória")
    sales = SaleRecord.objects.filter(tenant=tenant, channel="vidalys_flow",
                                      external_reference=ref)
    ensure(sales.count() == 1, "Pedido QA duplicado ou ausente")
    sale = sales.get()
    ensure(sale.customer_profile_id == profile.pk and sale.participant_id is None,
           "Unified ID não corresponde ao telefone comprovado")
    ensure(sale.order_status == SaleRecord.OrderStatus.PAID
           and sale.reported_total_cents == 1990 and sale.eligible_amount_cents == 0,
           "Valor, estado ou elegibilidade da venda divergente")
    ensure(SaleEventReceipt.objects.filter(sale=sale).count() == 2,
           "Inbox de eventos não preservou pending + paid sem duplicar")
    ensure(not FinancialEvidence.objects.filter(tenant=tenant, sale=sale).exists(),
           "Não é permitido criar evidência de PSP com evento sintético")
    ensure(not PointLot.objects.filter(tenant=tenant, source_reference=ref).exists(),
           "Crédito de pontos indevido")
    ensure(SaleRecord.objects.filter(tenant=tenant).count() == 1,
           "Teste QA contaminado por outras vendas")
    print("QA_DB_SMOKE_OK orders=1 inbox_events=2 unified_id=VERIFIED "
          "psp_evidence=0 grants=0 vouchers=0 points=0 cashback=0")


if __name__ == "__main__":
    try:
        main()
    except (GateFailed, ValueError) as exc:
        print("QA_DB_SMOKE_BLOCKED: " + str(exc), file=sys.stderr)
        sys.exit(2)
