"""Política única de operação do clube por loja: TESTE ou COMERCIAL.

Toda movimentação de saldo (pontos/giftback no balcão, ganho e cupom no site, motor do ledger)
pergunta aqui. Nada de DEBUG, branch, domínio ou lista no servidor.

- TESTE (padrão de toda loja): tudo funciona para testar, mas com tetos baixos e fixos.
  Mesmo numa loja real, a exposição máxima é pequena e conhecida.
- COMERCIAL: tetos maiores, liberado loja a loja pelo dono da plataforma (comando
  `set_store_operation`, só superusuário) e só enquanto os requisitos estiverem de pé.
  Requisito que cai bloqueia na hora (fail-closed), por canal.

Unidades: 1 unidade = R$ 0,01 de desconto (pontos e giftback usam o mesmo ledger).
"""
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

TEST = "test"
COMMERCIAL = "commercial"


@dataclass(frozen=True)
class Limits:
    per_sale: int   # máximo que UMA compra pode gerar
    budget: int     # máximo emitido no total pela loja


LIMITS = {
    TEST: Limits(per_sale=5_000, budget=200_000),            # R$ 50 por compra, R$ 2.000 no total
    COMMERCIAL: Limits(per_sale=20_000, budget=1_000_000),   # R$ 200 por compra, R$ 10.000 no total
}
STUCK_COUPON_AFTER = timedelta(hours=24)


def _pilot(tenant):
    from .models import CounterPilot
    return CounterPilot.objects.filter(tenant_id=getattr(tenant, "pk", tenant)).select_related("tenant").first()


def mode_of(pilot):
    return pilot.operation_mode if pilot is not None else TEST


def limits(pilot):
    return LIMITS[mode_of(pilot)]


def effective_per_sale(pilot):
    return min(pilot.per_sale_cap_points, limits(pilot).per_sale)


def effective_budget(pilot):
    return min(pilot.budget_points, limits(pilot).budget)


def _requirements(pilot):
    """(código, ok, texto para o lojista, canais afetados). Avaliado só no modo comercial."""
    from apps.participants.public_registration_views import active_terms_for, is_ready
    from .models import OnlineCoupon, PointRuleDraft, ProgramMode
    tenant = pilot.tenant
    rule = (ProgramMode.objects.filter(tenant=tenant, mode=ProgramMode.Mode.GIFTBACK).exists()
            or PointRuleDraft.objects.filter(tenant=tenant).exists())
    items = [
        ("terms", is_ready(active_terms_for(tenant)), "Regulamento e aviso de privacidade publicados", {"all"}),
        ("rule", rule, "Regra de pontos ou de giftback salva", {"all"}),
        ("approved", bool(pilot.commercial_at), "Modo comercial liberado pela Vidalys", {"all"}),
    ]
    if tenant.platform == "nuvemshop" and (pilot.online_earning or pilot.online_coupons):
        from .online import site_status
        status = site_status(tenant)
        stuck = OnlineCoupon.objects.filter(
            tenant=tenant, state__in=(OnlineCoupon.State.ISSUING, OnlineCoupon.State.UNCERTAIN),
            created_at__lte=timezone.now() - STUCK_COUPON_AFTER).exists()
        items += [
            # Pago reconsultado na Nuvemshop + avisos de cancelamento/reembolso = prova e estorno.
            ("site_payment", status["earning_ready"],
             "Pedidos pagos, cancelados e reembolsados chegando e sendo reconsultados", {"site_earn", "site_coupon"}),
            ("site_coupons", status["coupons_ready"], "Cupons liberados na Nuvemshop", {"site_coupon"}),
            ("coupons_settled", not stuck, "Nenhum cupom sem confirmação há mais de 24 horas", {"site_coupon"}),
        ]
    return items


def _failing(pilot, channel):
    """O que falta para o canal (None = todos, para o painel). Modo teste não tem bloqueios extras."""
    if pilot is None or mode_of(pilot) != COMMERCIAL:
        return []
    return [text for _code, ok, text, scope in _requirements(pilot)
            if not ok and (channel is None or "all" in scope or channel in scope)]


def blockers(pilot):
    return _failing(pilot, None)


def can_operate(tenant, channel="all"):
    """Clube ativo, loja ativa e, no comercial, requisitos do canal de pé.

    channel: "all" (balcão/ledger), "site_earn" (ganhar no site) ou "site_coupon" (cupom no site).
    """
    from apps.tenants.models import Tenant
    pilot = _pilot(tenant)
    if pilot is None or not pilot.active or pilot.tenant.status != Tenant.Status.ACTIVE:
        return False
    return not _failing(pilot, channel)


def snapshot(pilot):
    """Para o painel: modo, limites em R$ e o que falta."""
    lim = limits(pilot)
    data = {"mode": mode_of(pilot), "max_per_sale": lim.per_sale, "max_budget": lim.budget,
            "commercial_at": pilot.commercial_at.isoformat() if pilot is not None and pilot.commercial_at else None,
            "blockers": blockers(pilot)}
    if pilot is not None:
        data.update(effective_per_sale=effective_per_sale(pilot), effective_budget=effective_budget(pilot))
    return data


def has_club(tenant):
    from .models import CounterPilot
    return CounterPilot.objects.filter(tenant_id=getattr(tenant, "pk", tenant)).exists()


def ledger_write_allowed(tenant, *, settles):
    """Baixas e devoluções (resgate, estorno, vencimento) sempre podem acontecer: pausar o clube
    não pode deixar um cupom usado sem baixa. Crédito novo, liberação e reserva exigem operar."""
    return has_club(tenant) if settles else can_operate(tenant)
