"""Formatação pt-BR determinística (sem locale do sistema operacional)."""
from datetime import date, datetime


def _int(value, name):
    if type(value) is not int:
        raise ValueError(f"{name} deve ser inteiro.")
    return value


def _thousands(number):
    return f"{number:,}".replace(",", ".")


def brl(cents):
    """1234567 -> 'R$ 12.345,67'; negativos -> '-R$ 1,00'."""
    cents = _int(cents, "Centavos")
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {_thousands(reais)},{centavos:02d}"


def points(amount, *, short=False):
    """1 -> '1 ponto'; 1500 -> '1.500 pontos'; short=True -> '1.500 pts'."""
    amount = _int(amount, "Pontos")
    text = _thousands(amount)
    if short:
        return f"{text} pt" if abs(amount) == 1 else f"{text} pts"
    return f"{text} ponto" if abs(amount) == 1 else f"{text} pontos"


def days(amount):
    amount = _int(amount, "Dias")
    return "1 dia" if amount == 1 else f"{_thousands(amount)} dias"


def date_br(value):
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        raise ValueError("Data inválida.")
    return value.strftime("%d/%m/%Y")
