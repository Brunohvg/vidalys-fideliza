"""Saúde do Clube: prova de retorno honesta para o lojista.

O mercado vende "+27% de frequência" sem metodologia. Aqui o painel mostra
faixas, intervalos de confiança e "dados insuficientes" quando for o caso.
Diferença causal só é afirmada com grupo de controle e intervalo que não
cruza zero — regra do AGENTS.md ("sem grupo controle, não alegar aumento").
"""
import hashlib
import math
from dataclasses import dataclass
from fractions import Fraction

Z95 = 1.959963984540054


@dataclass(frozen=True)
class Liability:
    """Quanto os pontos em aberto podem custar, em faixa (centavos)."""
    low_cents: int | None
    high_cents: int | None
    basis: str  # "faixa" | "custo_desconhecido" | "sem_pontos"


def liability(points_outstanding, rewards):
    """Faixa de custo dos pontos em aberto pelo custo/ponto das recompensas ativas.

    Usa a recompensa mais barata e a mais cara por ponto: o lojista vê o
    cenário otimista e o conservador, sem um número falso de precisão.
    """
    if type(points_outstanding) is not int or points_outstanding < 0:
        raise ValueError("Pontos inválidos.")
    if points_outstanding == 0:
        return Liability(0, 0, "sem_pontos")
    per_point = [Fraction(r.merchant_cost_cents, r.points_cost)
                 for r in rewards
                 if r.available and r.merchant_cost_cents is not None]
    if not per_point:
        return Liability(None, None, "custo_desconhecido")
    return Liability(
        low_cents=math.floor(min(per_point) * points_outstanding),
        high_cents=math.ceil(max(per_point) * points_outstanding),
        basis="faixa",
    )


@dataclass(frozen=True)
class Rate:
    status: str  # "ok" | "dados_insuficientes"
    value: float | None
    low: float | None
    high: float | None
    successes: int
    total: int


def _wilson(successes, total):
    p = successes / total
    denominator = 1 + Z95 ** 2 / total
    center = (p + Z95 ** 2 / (2 * total)) / denominator
    margin = Z95 * math.sqrt(p * (1 - p) / total + Z95 ** 2 / (4 * total ** 2)) / denominator
    return p, max(0.0, center - margin), min(1.0, center + margin)


def rate(successes, total, *, min_total=30):
    """Taxa (ex.: recompra em 90 dias) com intervalo de Wilson 95%."""
    if (type(successes) is not int or type(total) is not int
            or successes < 0 or total < 0 or successes > total):
        raise ValueError("Contagens inválidas.")
    if total < min_total:
        return Rate("dados_insuficientes", None, None, None, successes, total)
    value, low, high = _wilson(successes, total)
    return Rate("ok", round(value, 4), round(low, 4), round(high, 4), successes, total)


@dataclass(frozen=True)
class Lift:
    status: str  # "dados_insuficientes" | "inconclusivo" | "positivo" | "negativo"
    difference: float | None
    low: float | None
    high: float | None


def lift(*, club_successes, club_total, control_successes, control_total, min_total=100):
    """Diferença entre grupo do clube e controle (Newcombe, IC 95%)."""
    for value in (club_successes, club_total, control_successes, control_total):
        if type(value) is not int or value < 0:
            raise ValueError("Contagens inválidas.")
    if club_successes > club_total or control_successes > control_total:
        raise ValueError("Contagens inválidas.")
    if club_total < min_total or control_total < min_total:
        return Lift("dados_insuficientes", None, None, None)
    p1, l1, u1 = _wilson(club_successes, club_total)
    p2, l2, u2 = _wilson(control_successes, control_total)
    diff = p1 - p2
    low = diff - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    high = diff + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    status = "positivo" if low > 0 else "negativo" if high < 0 else "inconclusivo"
    return Lift(status, round(diff, 4), round(low, 4), round(high, 4))


def in_message_holdout(*, tenant_id, participant_id, holdout_bps, salt):
    """Sorteio determinístico do grupo de controle de MENSAGENS (nunca de pontos).

    O cliente do controle continua acumulando e trocando normalmente; ele só
    não recebe campanhas não essenciais. ``holdout_bps`` em pontos-base (500 = 5%).
    """
    if type(holdout_bps) is not int or not 0 <= holdout_bps <= 5000:
        raise ValueError("Controle deve ficar entre 0% e 50%.")
    if not salt or not isinstance(salt, str):
        raise ValueError("Informe o sal do experimento.")
    digest = hashlib.sha256(f"{salt}:{tenant_id}:{participant_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 10_000 < holdout_bps
