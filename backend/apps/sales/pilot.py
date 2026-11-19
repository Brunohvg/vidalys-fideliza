"""Piloto de pontos no balcão: confirmar a venda libera os pontos; o vale é usado no caixa.

Portas de segurança (todas obrigatórias):
1. servidor em homologação (FIDELIZA_ENVIRONMENT=homolog);
2. loja listada em FIDELIZA_PILOT_TENANTS;
3. piloto ligado pelo proprietário no painel (CounterPilot.active).

As flags financeiras globais continuam desligadas. Sem custo de produto conferido,
o risco é limitado por teto de pontos por venda e orçamento total do piloto.
Nada aqui cria cupom na Nuvemshop nem movimenta cashback em reais.
"""
import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.participants.models import ProgramParticipant
from apps.points.models import PointEvent, PointLot, PointWallet
from apps.points.services import create_pending_lot, lot_balances, transition_points
from apps.tenants.models import Tenant

from .models import CounterPilot, CounterRedemption, DiscountRewardDraft, PointRuleDraft, ProgramMode, SaleRecord

RULE_PREFIX = "pilot-v"
HIGH_TICKET_MULTIPLIER = 10
FALLBACK_HIGH_CENTS = 200_000  # sem histórico: alerta acima de R$ 2.000
MIN_HISTORY = 5
UNDO_MINUTES = 5


class PilotBlocked(ValueError):
    pass


def _tenant_id(value):
    return str(getattr(value, "pk", value)).lower()


def pilot_allowed(tenant):
    """Servidor e lista de lojas permitem o piloto (sem olhar se está ligado)."""
    return (getattr(settings, "FIDELIZA_ENVIRONMENT", "") == "homolog"
            and _tenant_id(tenant) in getattr(settings, "FIDELIZA_PILOT_TENANTS", frozenset()))


def pilot_enabled(tenant):
    if not pilot_allowed(tenant):
        return False
    return CounterPilot.objects.filter(
        tenant_id=_tenant_id(tenant), active=True, tenant__status=Tenant.Status.ACTIVE,
    ).exists()


def source_reference(sale):
    return f"counter:{sale.pk}"


def issued_points(tenant_id):
    return PointLot.objects.filter(
        tenant_id=tenant_id, rule_version__startswith=RULE_PREFIX,
    ).aggregate(total=Sum("points_issued"))["total"] or 0


def _rule(tenant_id):
    return PointRuleDraft.objects.filter(tenant_id=tenant_id).first()


def program_mode(tenant_id):
    """Modo giftback configurado, ou None quando a loja usa pontos."""
    mode = ProgramMode.objects.filter(tenant_id=tenant_id).first()
    return mode if mode and mode.mode == ProgramMode.Mode.GIFTBACK else None


def mode_payload(tenant_id):
    gift = program_mode(tenant_id)
    if gift is None:
        return {"mode": "points"}
    return {"mode": "giftback", "percent_bps": gift.giftback_bps, "cap_cents": gift.giftback_cap_cents,
            "min_order_cents": gift.giftback_min_order_cents, "validity_days": gift.giftback_validity_days,
            "hold_days": gift.giftback_hold_days}


def _terms(tenant_id):
    """(hold_days, validity_days, rule_version) do modo em uso, ou None sem regra."""
    gift = program_mode(tenant_id)
    if gift:
        return gift.giftback_hold_days, gift.giftback_validity_days, f"{RULE_PREFIX}g{gift.version}"
    rule = _rule(tenant_id)
    return (rule.hold_days, rule.validity_days, f"{RULE_PREFIX}{rule.version}") if rule else None


def points_for(tenant_id, amount_cents):
    """Unidades a creditar (pontos, ou centavos no giftback), já com o teto do piloto. (valor, limitado?)"""
    if amount_cents <= 0:
        return 0, False
    gift = program_mode(tenant_id)
    if gift:
        raw = min(amount_cents * gift.giftback_bps // 10000, gift.giftback_cap_cents)
    else:
        rule = _rule(tenant_id)
        if rule is None:
            return 0, False
        raw = amount_cents * rule.points // rule.per_cents
    pilot = CounterPilot.objects.filter(tenant_id=tenant_id).first()
    cap = pilot.per_sale_cap_points if pilot else raw
    return min(raw, cap), raw > cap


def _notice_stats(tenant):
    from apps.participants.enrollment_models import EnrollmentSubmission
    from .models import CreditNotice
    reachable = EnrollmentSubmission.objects.filter(
        tenant=tenant, participant__status=ProgramParticipant.Status.ACTIVE, email_verified_at__isnull=False,
        withdrawn_at__isnull=True, marketing_opt_in=True,
    ).count()
    sent = CreditNotice.objects.filter(tenant=tenant, emailed=True).values("lot__wallet__participant", "kind").distinct().count()
    return {"reachable_members": reachable, "emails_queued": sent}


def pilot_state(tenant):
    pilot = CounterPilot.objects.filter(tenant=tenant).first()
    rule = _rule(tenant.pk)
    issued = issued_points(tenant.pk)
    return {
        "allowed": pilot_allowed(tenant),
        "active": bool(pilot and pilot.active and pilot_allowed(tenant)),
        "per_sale_cap_points": pilot.per_sale_cap_points if pilot else 1500,
        "budget_points": pilot.budget_points if pilot else 50000,
        "issued_points": issued,
        "activated_at": pilot.activated_at.isoformat() if pilot and pilot.activated_at else None,
        "paused_at": pilot.paused_at.isoformat() if pilot and pilot.paused_at else None,
        "rule": ({"points": rule.points, "per_cents": rule.per_cents,
                  "hold_days": rule.hold_days, "validity_days": rule.validity_days} if rule else None),
        "program": mode_payload(tenant.pk),
        "notices": _notice_stats(tenant),
        "counter_rewards": _rewards_qs(tenant.pk).count(),
    }


# ---------- Saldo e recompensas ----------

def _rewards_qs(tenant_id):
    now = timezone.now()
    return DiscountRewardDraft.objects.filter(
        tenant_id=tenant_id,
        publication_status=DiscountRewardDraft.PublicationStatus.PUBLISHED,
        redemption_unit="points", allowed_channels__contains="counter",
    ).filter(Q(valid_from__isnull=True) | Q(valid_from__lte=now)).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now),
    ).order_by("points_cost")


def _used(reward):
    return CounterRedemption.objects.filter(reward=reward).exclude(
        state=CounterRedemption.State.CANCELLED).count()


def _live_lots(wallet):
    return PointLot.objects.filter(wallet=wallet, expires_at__gt=timezone.now()).order_by("expires_at", "created_at")


def release_due(wallet):
    """Libera lotes cuja carência passou. Idempotente; chamado ao consultar o saldo."""
    if wallet is None or not pilot_enabled(wallet.tenant_id):
        return
    now = timezone.now()
    for lot in _live_lots(wallet).filter(unlock_at__lte=now):
        pending = lot_balances(lot)["pending"]
        if pending > 0:
            try:
                transition_points(lot_id=lot.pk, kind=PointEvent.Kind.RELEASE,
                                  amount=pending, idempotency_key=f"release:{lot.pk}")
            except (ValueError, PermissionError):
                continue


def wallet_balances(participant):
    wallet = PointWallet.objects.filter(participant=participant, tenant_id=participant.tenant_id).first()
    totals = {"pending": 0, "available": 0, "reserved": 0}
    if wallet is None:
        return wallet, totals
    for lot in _live_lots(wallet):
        for bucket, value in lot_balances(lot).items():
            totals[bucket] += value
    return wallet, totals


def counter_wallet(participant, *, amount_cents=0):
    """O que o vendedor vê ao achar a cliente: saldo, vales que dá para usar e a próxima meta."""
    wallet = PointWallet.objects.filter(participant=participant, tenant_id=participant.tenant_id).first()
    with transaction.atomic():
        release_due(wallet)
    _, totals = wallet_balances(participant)
    available = totals["available"]
    rewards = []
    for reward in _rewards_qs(participant.tenant_id):
        exhausted = _used(reward) >= reward.max_redemptions
        rewards.append({
            "id": str(reward.id), "title": reward.title, "points_cost": reward.points_cost,
            "discount_cents": reward.discount_cents, "min_order_cents": reward.min_order_cents,
            "affordable": available >= reward.points_cost and not exhausted,
            "exhausted": exhausted,
        })
    goal = next((r for r in rewards if not r["exhausted"] and r["points_cost"] > available), None)
    gift = program_mode(participant.tenant_id)
    if gift:
        rewards, goal = [], None
    return {
        "program": mode_payload(participant.tenant_id),
        "credit": ({"available_cents": available, "min_order_cents": gift.giftback_min_order_cents} if gift else None),
        "pilot_active": pilot_enabled(participant.tenant_id),
        "available": available, "pending": totals["pending"], "reserved": totals["reserved"],
        "rewards": rewards,
        "next_reward": ({"title": goal["title"], "points_cost": goal["points_cost"],
                         "missing": goal["points_cost"] - available,
                         "discount_cents": goal["discount_cents"]} if goal else None),
    }


# ---------- Vale no balcão ----------

def reserve_reward(*, sale, participant, reward_id, operator):
    """Reserva os pontos do vale na hora da venda. Chamar dentro de transação."""
    if not pilot_enabled(sale.tenant_id):
        raise PilotBlocked("O piloto de pontos não está ativo nesta loja.")
    if program_mode(sale.tenant_id):
        raise PilotBlocked("Esta loja usa giftback: aplique o crédito, não um vale de pontos.")
    reward = _rewards_qs(sale.tenant_id).filter(pk=reward_id).select_for_update().first()
    if reward is None:
        raise PilotBlocked("Vale não encontrado ou indisponível no balcão.")
    if _used(reward) >= reward.max_redemptions:
        raise PilotBlocked("Este vale atingiu o limite de usos.")
    if sale.eligible_amount_cents < reward.min_order_cents:
        raise PilotBlocked("A compra não atinge o valor mínimo deste vale.")
    if reward.discount_cents >= sale.eligible_amount_cents:
        raise PilotBlocked("O vale não pode ser maior que a compra.")
    wallet = PointWallet.objects.filter(participant=participant, tenant_id=sale.tenant_id).first()
    release_due(wallet)
    _, totals = wallet_balances(participant)
    if totals["available"] < reward.points_cost:
        raise PilotBlocked("A cliente não tem pontos liberados suficientes para este vale.")
    return _reserve(sale=sale, participant=participant, wallet=wallet, amount=reward.points_cost,
                    discount_cents=reward.discount_cents, reward=reward, operator=operator)


def reserve_credit(*, sale, participant, operator):
    """Giftback: usa todo o crédito liberado da cliente nesta compra (pedido mínimo da loja)."""
    if not pilot_enabled(sale.tenant_id):
        raise PilotBlocked("O piloto não está ativo nesta loja.")
    gift = program_mode(sale.tenant_id)
    if gift is None:
        raise PilotBlocked("Esta loja usa pontos, não giftback.")
    if sale.eligible_amount_cents < gift.giftback_min_order_cents:
        raise PilotBlocked("A compra não atinge o valor mínimo para usar o crédito.")
    wallet = PointWallet.objects.filter(participant=participant, tenant_id=sale.tenant_id).first()
    release_due(wallet)
    _, totals = wallet_balances(participant)
    amount = totals["available"]
    if amount <= 0:
        raise PilotBlocked("A cliente não tem crédito liberado agora.")
    if amount >= sale.eligible_amount_cents:
        raise PilotBlocked("O crédito não pode ser maior que a compra.")
    return _reserve(sale=sale, participant=participant, wallet=wallet, amount=amount,
                    discount_cents=amount, reward=None, operator=operator)


def _reserve(*, sale, participant, wallet, amount, discount_cents, reward, operator):
    remaining, allocations = amount, []
    for lot in _live_lots(wallet):
        if remaining == 0:
            break
        take = min(lot_balances(lot)["available"], remaining)
        if take <= 0:
            continue
        transition_points(lot_id=lot.pk, kind=PointEvent.Kind.RESERVE, amount=take,
                          idempotency_key=f"pilot-reserve:{sale.pk}")
        allocations.append({"lot": str(lot.pk), "amount": take})
        remaining -= take
    if remaining:
        raise PilotBlocked("Saldo mudou durante a operação. Tente de novo.")
    return CounterRedemption.objects.create(
        tenant_id=sale.tenant_id, sale=sale, participant=participant, reward=reward,
        points=amount, discount_cents=discount_cents,
        allocations=allocations, created_by=operator,
    )


def settle_redemption(sale, *, approve):
    redemption = CounterRedemption.objects.select_for_update().filter(sale=sale).first()
    if redemption is None or redemption.state != CounterRedemption.State.RESERVED:
        return redemption
    kind = PointEvent.Kind.REDEEM if approve else PointEvent.Kind.CANCEL_RESERVE
    key = f"pilot-{'redeem' if approve else 'cancel'}:{sale.pk}"
    for item in redemption.allocations:
        transition_points(lot_id=item["lot"], kind=kind, amount=item["amount"], idempotency_key=key,
                          external_receipt=source_reference(sale) if approve else "")
    redemption.state = CounterRedemption.State.REDEEMED if approve else CounterRedemption.State.CANCELLED
    redemption.settled_at = timezone.now()
    redemption.save(update_fields=["state", "settled_at"])
    return redemption


# ---------- Conferência ----------

def grant_for_review(sale, reviewer):
    """Venda confirmada pelo lojista vira pontos pendentes. Retorna (pontos, motivo)."""
    if not pilot_enabled(sale.tenant_id):
        return 0, "pilot_off"
    participant = sale.participant
    if participant is None or participant.status != ProgramParticipant.Status.ACTIVE:
        return 0, "no_participant"
    pilot = CounterPilot.objects.select_for_update().get(tenant_id=sale.tenant_id)
    terms = _terms(sale.tenant_id)
    if terms is None:
        return 0, "no_rule"
    hold_days, validity_days, rule_version = terms
    redemption = getattr(sale, "counter_redemption", None)
    discount = redemption.discount_cents if redemption and redemption.state != CounterRedemption.State.CANCELLED else 0
    base = sale.eligible_amount_cents - discount
    points, _capped = points_for(sale.tenant_id, base)
    if points <= 0:
        return 0, "zero"
    left = pilot.budget_points - issued_points(sale.tenant_id)
    if left <= 0:
        return 0, "budget"
    points = min(points, left)
    paid_at = sale.reported_paid_at or sale.created_at
    if paid_at < max(participant.joined_at, participant.consent_at):
        return 0, "before_join"
    now = timezone.now()
    unlock_at = max(now, paid_at) + timedelta(days=hold_days)
    digest = hashlib.sha256(f"{sale.pk}|{reviewer.pk}|{base}|{points}".encode()).hexdigest()
    create_pending_lot(
        participant=participant, channel=SaleRecord.Channel.COUNTER,
        source_reference=source_reference(sale), eligible_amount_cents=base, points=points,
        rule_version=rule_version, paid_at=paid_at, unlock_at=unlock_at,
        expires_at=unlock_at + timedelta(days=validity_days), verification_digest=digest,
    )
    return points, "granted"


def sale_lot(sale):
    return PointLot.objects.filter(tenant_id=sale.tenant_id, source_reference=source_reference(sale)).first()


# ---------- Alertas ----------

def average_ticket(tenant_id):
    since = timezone.now() - timedelta(days=90)
    row = SaleRecord.objects.filter(
        tenant_id=tenant_id, channel=SaleRecord.Channel.COUNTER,
        state=SaleRecord.State.VERIFIED_MANUAL, created_at__gte=since,
    ).aggregate(avg=Avg("eligible_amount_cents"), n=Count("id"))
    return int(row["avg"]) if row["n"] and row["n"] >= MIN_HISTORY else 0


def sale_alerts(sale, avg_ticket):
    alerts = []
    amount = sale.eligible_amount_cents
    if avg_ticket and amount >= HIGH_TICKET_MULTIPLIER * avg_ticket:
        alerts.append(f"{amount // avg_ticket}× o ticket médio")
    elif not avg_ticket and amount > FALLBACK_HIGH_CENTS:
        alerts.append("valor acima de R$ 2.000")
    hour = timezone.localtime(sale.created_at).hour
    if hour < 7 or hour >= 22:
        alerts.append("registrada fora do horário comercial")
    if sale.participant_id:
        window = (sale.created_at - timedelta(hours=24), sale.created_at + timedelta(hours=24))
        same_day = SaleRecord.objects.filter(
            tenant_id=sale.tenant_id, channel=SaleRecord.Channel.COUNTER,
            participant_id=sale.participant_id, created_at__range=window,
        ).exclude(state=SaleRecord.State.REJECTED).count()
        if same_day >= 3:
            alerts.append(f"{same_day} vendas da mesma cliente em 24 h")
    return alerts


def can_undo(sale, user_id):
    return (sale.submitted_by_id == user_id
            and sale.state in (SaleRecord.State.AWAITING_REVIEW, SaleRecord.State.AWAITING_MEMBER)
            and timezone.now() - sale.created_at <= timedelta(minutes=UNDO_MINUTES))
