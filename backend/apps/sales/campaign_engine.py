"""Motor de campanhas: quem recebe, quanto custa no máximo e o que aconteceu.

Regras:
- Público calculado só com dados reais da loja (participantes ativos e vendas
  registradas). Sem dado, o público é zero; nunca estimado.
- Grupo de comparação determinístico (hash da campanha + participante): a mesma
  pessoa fica sempre no mesmo grupo, sem tabela extra.
- 1 ponto = R$ 0,01. Custo máximo = clientes alcançados × pontos de bônus.
- Nada aqui credita pontos, cria cupom ou envia mensagem.
"""
import hashlib
from datetime import datetime, time, timedelta

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import DiscountRewardDraft, PointCampaignDraft, SaleRecord

GOALS = PointCampaignDraft.Goal
COUNTED = ~Q(state=SaleRecord.State.REJECTED) & ~Q(
    order_status__in=[SaleRecord.OrderStatus.CANCELLED, SaleRecord.OrderStatus.REFUNDED])


def bucket(campaign_id, participant_id):
    raw = hashlib.sha256(f"fideliza:campaign:{campaign_id}:{participant_id}".encode()).digest()
    return int.from_bytes(raw[:4], "big") % 10_000


def _active(tenant_id):
    from apps.participants.models import ProgramParticipant
    return ProgramParticipant.objects.filter(
        tenant_id=tenant_id, status=ProgramParticipant.Status.ACTIVE)


def _purchases(tenant_id, as_of):
    return (SaleRecord.objects.filter(tenant_id=tenant_id, participant__isnull=False)
            .filter(COUNTED)
            .annotate(at=Coalesce("reported_paid_at", "created_at")).filter(at__lt=as_of)
            .values("participant_id")
            .annotate(n=Count("id"), last=Max(Coalesce("reported_paid_at", "created_at"))))


def _cheapest_reward(tenant_id):
    item = (DiscountRewardDraft.objects.filter(tenant_id=tenant_id, published_at__isnull=False)
            .order_by("points_cost").first())
    return item.points_cost if item else None


def _balances(tenant_id, participant_ids):
    """Saldo disponível por participante, só de lotes válidos."""
    from apps.points.models import PointEntry
    now = timezone.now()
    rows = (PointEntry.objects.filter(
        event__lot__tenant_id=tenant_id, event__lot__wallet__participant_id__in=participant_ids,
        event__lot__expires_at__gt=now, bucket="available")
        .values("event__lot__wallet__participant_id").annotate(total=Sum("delta")))
    return {row["event__lot__wallet__participant_id"]: row["total"] or 0 for row in rows}


def start_of(day):
    return timezone.make_aware(datetime.combine(day, time.min)) if day else None


def eligible_ids(tenant_id, goal, *, window_days=30, inactive_days=60, near_points=100,
                 month=None, as_of=None):
    """IDs de participantes ativos que se encaixam na regra, sem grupo de comparação.

    as_of fixa o público no início da campanha: quem volta a comprar durante a
    campanha continua no mesmo grupo, e a comparação de resultado fica justa."""
    now = timezone.now()
    as_of = min(as_of or now, now)
    today = timezone.localdate(as_of)
    active = list(_active(tenant_id).values_list("id", flat=True))
    if not active:
        return []
    if goal in (GOALS.MULTIPLIER, GOALS.RECURRENCE):
        return active
    if goal == GOALS.BIRTHDAY:
        from apps.participants.enrollment_models import EnrollmentSubmission
        wanted = month or today.month
        return list(EnrollmentSubmission.objects.filter(
            tenant_id=tenant_id, participant_id__in=active, birth_month=wanted,
            withdrawn_at__isnull=True).values_list("participant_id", flat=True))
    if goal == GOALS.NEAR_REWARD:
        cheapest = _cheapest_reward(tenant_id)
        if not cheapest:
            return []
        floor = max(0, cheapest - near_points)
        return [pid for pid, total in _balances(tenant_id, active).items()
                if floor <= total < cheapest]
    stats = {row["participant_id"]: row for row in _purchases(tenant_id, as_of).filter(participant_id__in=active)}
    if goal == GOALS.SECOND:
        limit = as_of - timedelta(days=window_days)
        return [pid for pid, row in stats.items() if row["n"] == 1 and row["last"] and row["last"] >= limit]
    if goal == GOALS.REACTIVATION:
        limit = as_of - timedelta(days=inactive_days)
        return [pid for pid, row in stats.items() if row["last"] and row["last"] < limit]
    return []


def split(campaign_id, ids, holdout_percent, max_customers):
    """(alcançados, comparação). Ordem estável pelo hash; respeita o limite de clientes."""
    ranked = sorted(ids, key=lambda pid: bucket(campaign_id, pid))
    cut = holdout_percent * 100
    control = [pid for pid in ranked if bucket(campaign_id, pid) < cut]
    treated = [pid for pid in ranked if bucket(campaign_id, pid) >= cut][:max_customers]
    return treated, control


def audience(campaign_id, tenant_id, params):
    month = params["starts_on"].month if params.get("starts_on") else None
    ids = eligible_ids(tenant_id, params["goal"], window_days=params["window_days"],
                       inactive_days=params["inactive_days"], near_points=params["near_points"],
                       month=month, as_of=start_of(params.get("starts_on")))
    treated, control = split(campaign_id, ids, params["holdout_percent"], params["max_customers"])
    return {
        "eligible": len(ids), "reached": len(treated), "comparison": len(control),
        "max_cost_cents": len(treated) * params["bonus_points"],
        "max_cost_if_full_cents": params["max_customers"] * params["bonus_points"],
    }


def params_of(obj):
    return {field: getattr(obj, field) for field in (
        "goal", "bonus_points", "max_customers", "window_days", "inactive_days",
        "near_points", "holdout_percent", "starts_on")}


def phase(obj, today=None):
    today = today or timezone.localdate()
    if not obj.published_at:
        return "draft"
    if obj.ends_on and obj.ends_on < today:
        return "ended"
    if obj.starts_on and obj.starts_on > today:
        return "scheduled"
    return "live"


def result(obj):
    """Voltou a comprar desde o início: quem recebeu × grupo de comparação.
    Comparação simples, sem teste estatístico: serve de sinal, não de prova."""
    if not obj.published_at or not obj.starts_on or obj.starts_on > timezone.localdate():
        return None
    params = params_of(obj)
    since = start_of(obj.starts_on)
    ids = eligible_ids(obj.tenant_id, obj.goal, window_days=obj.window_days,
                       inactive_days=obj.inactive_days, near_points=obj.near_points,
                       month=obj.starts_on.month, as_of=since)
    treated, control = split(obj.id, ids, params["holdout_percent"], params["max_customers"])
    until = start_of(obj.ends_on + timedelta(days=1)) if obj.ends_on else None
    base = SaleRecord.objects.filter(tenant_id=obj.tenant_id).filter(COUNTED).annotate(
        at=Coalesce("reported_paid_at", "created_at")).filter(at__gte=since)
    if until:
        base = base.filter(at__lt=until)

    def returned(group):
        if not group:
            return 0
        return base.filter(participant_id__in=group).values("participant_id").distinct().count()

    return {"reached": len(treated), "reached_returned": returned(treated),
            "comparison": len(control), "comparison_returned": returned(control)}


def offers_for(tenant_id, participant_id, today=None):
    """Campanhas no ar que valem para este participante (fora do grupo de comparação)."""
    today = today or timezone.localdate()
    live = PointCampaignDraft.objects.filter(
        tenant_id=tenant_id, published_at__isnull=False,
    ).filter(Q(starts_on__isnull=True) | Q(starts_on__lte=today)).filter(
        Q(ends_on__isnull=True) | Q(ends_on__gte=today))
    found = []
    for obj in live[:10]:
        ids = eligible_ids(tenant_id, obj.goal, window_days=obj.window_days,
                           inactive_days=obj.inactive_days, near_points=obj.near_points,
                           month=obj.starts_on.month if obj.starts_on else None,
                           as_of=start_of(obj.starts_on) or obj.published_at)
        if participant_id not in ids:
            continue
        treated, _ = split(obj.id, ids, obj.holdout_percent, obj.max_customers)
        if participant_id in treated:
            found.append(present_offer(obj))
    return found


DEFAULT_TEXT = {
    GOALS.SECOND: ("Volte e ganhe +{p} pontos", "Na sua próxima compra até {d}, você ganha {p} pontos extras."),
    GOALS.REACTIVATION: ("Sentimos sua falta: +{p} pontos", "Compre até {d} e ganhe {p} pontos extras."),
    GOALS.RECURRENCE: ("Compre de novo e ganhe +{p} pontos", "Cada compra até {d} rende {p} pontos extras."),
    GOALS.NEAR_REWARD: ("Você está quase lá", "Compre até {d} e ganhe {p} pontos extras para completar sua troca."),
    GOALS.MULTIPLIER: ("Pontos em dobro", "Compras até {d} valem {m}× pontos (até {p} pontos extras)."),
    GOALS.BIRTHDAY: ("Feliz aniversário! +{p} pontos", "Presente da loja: compre até {d} e ganhe {p} pontos extras."),
}


def default_text(obj):
    title, message = DEFAULT_TEXT.get(obj.goal, ("Oferta para você", "Ganhe {p} pontos extras até {d}."))
    when = obj.ends_on.strftime("%d/%m") if obj.ends_on else "o fim da campanha"
    fill = {"p": f"{obj.bonus_points:,}".replace(",", "."), "d": when, "m": obj.multiplier}
    return title.format(**fill), message.format(**fill)


def present_offer(obj):
    title, message = default_text(obj)
    return {
        "id": str(obj.id), "goal": obj.goal,
        "title": obj.title or title, "message": obj.message or message,
        "bonus_points": obj.bonus_points,
        "multiplier": obj.multiplier if obj.goal == GOALS.MULTIPLIER else None,
        "ends_on": obj.ends_on.isoformat() if obj.ends_on else None,
    }
