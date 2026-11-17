"""Reconhecimento sem spam: marcos do cliente com limite de frequência.

Dor medida: só 23,9% se sentem reconhecidos com frequência; NPS 60 contra 22
de quem não se sente. E 62,4% preferem poucas mensagens (Panorama 2026).
Por isso o marco aparece SEMPRE dentro do clube e só vira mensagem se o
limite de frequência permitir.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

PURCHASE_MARKS = (1, 3, 5, 10, 25, 50, 100)


@dataclass(frozen=True)
class Milestone:
    key: str
    title: str
    message: str


def _anniversary(joined_on, year):
    try:
        return joined_on.replace(year=year)
    except ValueError:  # 29/02 em ano não bissexto
        return date(year, 2, 28)


def detect(*, purchases, previous_purchases, redemptions, previous_redemptions,
           joined_on, today, level=None, previous_level=None):
    """Marcos novos entre o estado anterior e o atual (chaves idempotentes)."""
    for name, value in (("purchases", purchases), ("previous_purchases", previous_purchases),
                        ("redemptions", redemptions),
                        ("previous_redemptions", previous_redemptions)):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} inválido.")
    if not isinstance(joined_on, date) or not isinstance(today, date):
        raise ValueError("Datas inválidas.")
    found = []
    for mark in PURCHASE_MARKS:
        if previous_purchases < mark <= purchases:
            if mark == 1:
                found.append(Milestone("purchases:1", "Primeira compra no clube",
                                       "Seus primeiros pontos já estão a caminho."))
            else:
                found.append(Milestone(f"purchases:{mark}", f"{mark} compras com a gente",
                                       f"Obrigado por voltar! Esta foi sua {mark}ª compra no clube."))
    if previous_redemptions == 0 and redemptions > 0:
        found.append(Milestone("redemption:first", "Primeira troca",
                               "Você trocou seus pontos pela primeira vez. Aproveite!"))
    years = today.year - joined_on.year
    if years >= 1 and _anniversary(joined_on, today.year) == today:
        found.append(Milestone(f"anniversary:{today.year}",
                               f"{years} {'ano' if years == 1 else 'anos'} de clube",
                               "Obrigado por fazer parte do clube."))
    if level and level != previous_level and previous_level is not None:
        found.append(Milestone(f"level:{level}", f"Você agora é {level}",
                               f"Você subiu para o nível {level}."))
    return found


def may_message(*, last_message_at, now, min_interval_days=7):
    """Limite de frequência de mensagens não essenciais (marcos, campanhas)."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Agora precisa ter fuso horário.")
    if last_message_at is None:
        return True
    return now - last_message_at >= timedelta(days=min_interval_days)
