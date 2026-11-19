"""Resultado do clube por loja, só com registros reais do Fideliza (ledger + vendas).

Cada lote do clube é uma compra conferida (balcão) ou paga (site). Valores em centavos:
no giftback 1 unidade = R$ 0,01; nos pontos também (1 ponto = R$ 0,01 de desconto).
Sem grupo de controle, a tela NÃO afirma que o clube causou as vendas.
"""
from datetime import timedelta

from django.db.models import Count, Min, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.points.models import PointEvent, PointLot
from apps.points.services import lot_balances

from .models import CounterRedemption, OnlineCoupon, SaleRecord
from .pilot import RULE_PREFIX, mode_payload


def _sum(qs, field):
    return qs.aggregate(total=Sum(field))["total"] or 0


def club_results(tenant, *, days=30):
    now = timezone.now()
    since = now - timedelta(days=days)
    lots = PointLot.objects.filter(tenant=tenant, rule_version__startswith=RULE_PREFIX)
    period = lots.filter(created_at__gte=since)

    revenue = _sum(period, "eligible_amount_cents")
    issued = _sum(period, "points_issued")
    buyers = set(period.values_list("wallet__participant_id", flat=True))
    first_purchase = dict(lots.values("wallet__participant_id").annotate(first=Min("created_at"))
                          .values_list("wallet__participant_id", "first"))
    returning = {p for p in buyers if first_purchase.get(p) and first_purchase[p] < since}
    repeat_in_period = {row["wallet__participant_id"] for row in
                        period.values("wallet__participant_id").annotate(n=Count("id")).filter(n__gte=2)}
    came_back = returning | repeat_in_period

    events = PointEvent.objects.filter(lot__in=lots, created_at__gte=since)
    # Uso tardio de cupom do site é baixa direta com o pedido como comprovante: conta como usado.
    late_use = events.filter(kind=PointEvent.Kind.REVERSE_AVAILABLE, external_receipt__startswith="site:")
    used = _sum(events.filter(kind=PointEvent.Kind.REDEEM), "amount") + _sum(late_use, "amount")
    expired = _sum(events.filter(kind__in=(PointEvent.Kind.EXPIRE_PENDING, PointEvent.Kind.EXPIRE_AVAILABLE)), "amount")
    reversed_ = _sum(events.filter(kind__in=(PointEvent.Kind.REVERSE_PENDING, PointEvent.Kind.REVERSE_AVAILABLE))
                     .exclude(pk__in=late_use.values("pk")), "amount")

    # Desconto efetivamente concedido (valor em reais do vale/crédito) e a venda que ele puxou.
    counter_used = CounterRedemption.objects.filter(tenant=tenant, state=CounterRedemption.State.REDEEMED,
                                                    settled_at__gte=since).select_related("sale")
    site_used = OnlineCoupon.objects.filter(tenant=tenant, state=OnlineCoupon.State.USED, settled_at__gte=since)
    discount = sum(r.discount_cents for r in counter_used) + sum(c.discount_cents for c in site_used)
    site_orders = {f"site:{c.used_order_id}" for c in site_used if c.used_order_id}
    pulled = (sum(r.sale.eligible_amount_cents for r in counter_used)
              + _sum(lots.filter(source_reference__in=site_orders), "eligible_amount_cents"))

    open_total = {"pending": 0, "available": 0, "reserved": 0}
    for lot in lots.filter(expires_at__gt=now):
        for bucket, value in lot_balances(lot).items():
            open_total[bucket] += value

    months = []
    start = (now.replace(day=1) - timedelta(days=150)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    issued_by = dict(lots.filter(created_at__gte=start).annotate(m=TruncMonth("created_at"))
                     .values("m").annotate(t=Sum("points_issued")).values_list("m", "t"))
    used_by = dict(PointEvent.objects.filter(lot__in=lots, kind=PointEvent.Kind.REDEEM, created_at__gte=start)
                   .annotate(m=TruncMonth("created_at")).values("m").annotate(t=Sum("amount")).values_list("m", "t"))
    cursor = start
    for _ in range(6):
        key = cursor.date()
        months.append({"month": key.isoformat(),
                       "issued": next((v for k, v in issued_by.items() if k.date() == key), 0) or 0,
                       "used": next((v for k, v in used_by.items() if k.date() == key), 0) or 0})
        cursor = (cursor + timedelta(days=32)).replace(day=1)

    counter_sales = SaleRecord.objects.filter(tenant=tenant, channel=SaleRecord.Channel.COUNTER,
                                              created_at__gte=since).exclude(state=SaleRecord.State.REJECTED)
    with_member = counter_sales.filter(participant__isnull=False)
    return {
        "days": days, "program": mode_payload(tenant.pk),
        "members_active": ProgramParticipant.objects.filter(tenant=tenant, status=ProgramParticipant.Status.ACTIVE).count(),
        "purchases": period.count(), "revenue_cents": revenue, "buyers": len(buyers),
        "came_back": len(came_back), "issued": issued, "used": used, "expired": expired, "reversed": reversed_,
        "discount_cents": discount, "pulled_revenue_cents": pulled,
        "cost_bps": round(discount * 10000 / revenue) if revenue else None,
        "open": open_total, "months": months,
        "counter": {"sales": counter_sales.count(), "with_member": with_member.count(),
                    "member_cents": _sum(with_member, "eligible_amount_cents"),
                    "other_cents": _sum(counter_sales.filter(participant__isnull=True), "eligible_amount_cents")},
        "causal_claim": False,
    }
