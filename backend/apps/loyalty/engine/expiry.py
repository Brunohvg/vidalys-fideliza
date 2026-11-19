"""Pontos sem Susto: validade renovável e aviso consolidado.

Dor medida: vencer pontos é o motivo nº 1 de abandono (19,9%); 64,7%
descobriram um benefício tarde demais; 43,2% querem aviso antes (Panorama 2026).

O ledger (``points.PointLot``) é imutável: a validade renovada é CALCULADA a
partir da data de liberação e das compras posteriores, nunca gravada por
UPDATE. Quem expira de fato continua sendo a transição ``expire_*``.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .rules import EXPIRY_FIXED, EXPIRY_ROLLING

DAY = timedelta(days=1)


def _aware(value, name):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} precisa ter fuso horário.")
    return value


def effective_expiry(rule, *, released_at, activity=()):
    """Data de vencimento efetiva de um lote liberado.

    Renovável: cada compra elegível ANTES do vencimento corrente empurra o prazo
    para ``compra + validade``, limitado por ``renewal_cap_days``. Compra depois
    do vencimento não ressuscita pontos.
    """
    _aware(released_at, "Liberação")
    expires = released_at + timedelta(days=rule.validity_days)
    if rule.expiry_policy == EXPIRY_FIXED:
        return expires
    cap = (released_at + timedelta(days=rule.renewal_cap_days)
           if rule.renewal_cap_days else None)
    for moment in sorted(_aware(a, "Compra") for a in activity):
        if moment < released_at:
            continue
        if moment >= expires:
            break
        expires = max(expires, moment + timedelta(days=rule.validity_days))
        if cap is not None:
            expires = min(expires, cap)
    return expires


@dataclass(frozen=True)
class ExpiringLot:
    participant_id: str
    lot_id: str
    points: int
    expires_at: datetime


@dataclass(frozen=True)
class Notice:
    participant_id: str
    offset_days: int
    points: int
    earliest_expiry: datetime
    dedupe_keys: tuple = field(default_factory=tuple)


def days_left(expires_at, now):
    """Dias restantes arredondados para cima (vence hoje = 1)."""
    seconds = (expires_at - now).total_seconds()
    return -int(-seconds // DAY.total_seconds())


def plan_notices(lots, *, now, offsets=(30, 7, 1), already_sent=frozenset()):
    """Uma mensagem por participante, no marco mais urgente ainda não enviado.

    ``already_sent`` contém chaves ``"<lot_id>:<offset>"``. Um lote que entrou
    tarde no radar (ex.: 5 dias restantes) recebe o marco de 7, não o de 30.
    """
    _aware(now, "Agora")
    marks = sorted({o for o in offsets if type(o) is int and o > 0})
    if not marks:
        return []
    grouped = {}
    for lot in lots:
        _aware(lot.expires_at, "Vencimento")
        if lot.points <= 0 or lot.expires_at <= now:
            continue
        remaining = days_left(lot.expires_at, now)
        offset = next((m for m in marks if remaining <= m), None)
        if offset is None:
            continue
        key = f"{lot.lot_id}:{offset}"
        if key in already_sent:
            continue
        grouped.setdefault(lot.participant_id, []).append((offset, lot, key))
    notices = []
    for participant_id in sorted(grouped):
        rows = grouped[participant_id]
        notices.append(Notice(
            participant_id=participant_id,
            offset_days=min(offset for offset, _, _ in rows),
            points=sum(lot.points for _, lot, _ in rows),
            earliest_expiry=min(lot.expires_at for _, lot, _ in rows),
            dedupe_keys=tuple(sorted(key for _, _, key in rows)),
        ))
    return notices


def exposure(lots, *, now, horizon_days=30):
    """Pontos que vencem nos próximos ``horizon_days`` (painel do lojista)."""
    _aware(now, "Agora")
    limit = now + timedelta(days=horizon_days)
    return sum(lot.points for lot in lots
               if lot.points > 0 and now < _aware(lot.expires_at, "Vencimento") <= limit)


def notice_message(notice, *, store_name, club_url):
    """Texto curto e acionável (sem dado pessoal além do saldo)."""
    from . import formatting as fmt
    when = ("hoje" if notice.offset_days <= 1 else
            f"em até {fmt.days(notice.offset_days)}")
    return (f"{store_name}: {fmt.points(notice.points)} do seu clube vencem {when} "
            f"(a partir de {fmt.date_br(notice.earliest_expiry)}). "
            f"Veja o que dá para trocar: {club_url}")
