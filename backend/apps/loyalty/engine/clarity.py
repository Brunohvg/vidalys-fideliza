"""Clube Claro: a regra explicada em frases curtas e o selo de clareza.

Dor medida: só 53,2% dos participantes acham as regras claras; o NPS é 55
entre quem entende e 20 entre quem precisa se esforçar (Panorama 2026).
O selo só é concedido quando todos os itens obrigatórios passam.
"""
import re
from dataclasses import dataclass, field

from . import formatting as fmt
from .rules import EXPIRY_ROLLING, minimum_spend_cents, points_for

DEFAULT_NOTICE_OFFSETS = (30, 7, 1)
MIN_TERMS_LENGTH = 200
PLACEHOLDER = re.compile(
    r"\bX{2,}\b|\?{3,}|lorem ipsum|\{\{|\}\}|\[(?:inserir|preencher|definir)[^\]]*\]"
    r"|\bTODO\b|\bA DEFINIR\b|\bTBD\b",
    re.IGNORECASE,
)


def describe(rule, *, notice_offsets=DEFAULT_NOTICE_OFFSETS, example_cents=10_000):
    """Frases em pt-BR, na ordem em que o cliente precisa delas."""
    headline = f"Cada {fmt.brl(rule.per_cents)} em compras vale {fmt.points(rule.points)}."
    fraction_cents = rule.per_cents * 10 - 1
    sentences = [
        headline,
        "Centavos que não completam a faixa não somam: uma compra de "
        f"{fmt.brl(fraction_cents)} gera {fmt.points(points_for(rule, fraction_cents))}.",
    ]
    if rule.hold_days == 0:
        sentences.append("Os pontos ficam disponíveis assim que a compra é confirmada.")
    else:
        sentences.append(
            f"Os pontos ficam pendentes por {fmt.days(rule.hold_days)} depois da compra "
            "confirmada (prazo de trocas e devoluções) e então são liberados."
        )
    if rule.expiry_policy == EXPIRY_ROLLING:
        text = (f"Depois de liberados, valem por {fmt.days(rule.validity_days)}, e cada nova "
                "compra renova o prazo de todos os seus pontos")
        if rule.renewal_cap_days:
            text += f" (até {fmt.days(rule.renewal_cap_days)} contados da liberação)"
        sentences.append(text + ".")
    else:
        sentences.append(f"Depois de liberados, valem por {fmt.days(rule.validity_days)}.")
    offsets = sorted({o for o in notice_offsets if type(o) is int and o > 0}, reverse=True)
    if offsets:
        sentences.append("Avisamos você " + _join([str(o) for o in offsets])
                         + (" dia" if offsets == [1] else " dias")
                         + " antes de qualquer ponto vencer.")
    sentences.append(f"Exemplo: uma compra de {fmt.brl(example_cents)} gera "
                     f"{fmt.points(points_for(rule, example_cents))}.")
    return {"headline": headline, "sentences": sentences}


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


@dataclass(frozen=True)
class CheckItem:
    key: str
    label: str
    ok: bool
    required: bool
    detail: str = ""


@dataclass(frozen=True)
class ClarityReport:
    items: list = field(default_factory=list)

    @property
    def seal(self):
        return all(item.ok for item in self.items if item.required)

    @property
    def pending(self):
        return [item for item in self.items if item.required and not item.ok]

    def as_dict(self):
        return {
            "seal": self.seal,
            "items": [item.__dict__ for item in self.items],
        }


def checklist(rule, *, terms_text, rewards, notice_offsets=DEFAULT_NOTICE_OFFSETS):
    """Selo de clareza. ``rewards`` = lista de ``goals.Reward`` publicadas."""
    text = terms_text if isinstance(terms_text, str) else ""
    items = []
    placeholder = PLACEHOLDER.search(text)
    items.append(CheckItem(
        "regulamento_completo", "Regulamento completo, sem lacunas", required=True,
        ok=len(text.strip()) >= MIN_TERMS_LENGTH and placeholder is None,
        detail=(f"Trecho pendente: “{placeholder.group(0)}”." if placeholder else
                "" if len(text.strip()) >= MIN_TERMS_LENGTH else
                f"Escreva pelo menos {MIN_TERMS_LENGTH} caracteres."),
    ))
    numbers = [rule.validity_days] + ([rule.hold_days] if rule.hold_days else [])
    missing = [n for n in numbers if not re.search(rf"(?<!\d){n}(?!\d)", text)]
    items.append(CheckItem(
        "regulamento_igual_ao_motor", "Regulamento cita os mesmos prazos da regra",
        required=True, ok=not missing,
        detail="" if not missing else
        "Prazos ausentes no texto: " + ", ".join(fmt.days(n) for n in missing) + ".",
    ))
    published = [r for r in rewards if getattr(r, "active", False)]
    cheapest = min(published, key=lambda r: r.points_cost, default=None)
    items.append(CheckItem(
        "recompensa_publicada", "Pelo menos uma recompensa publicada", required=True,
        ok=cheapest is not None,
        detail="" if cheapest is None else
        f"A mais acessível pede {fmt.points(cheapest.points_cost)} "
        f"(gasto mínimo de {fmt.brl(minimum_spend_cents(rule, cheapest.points_cost))}).",
    ))
    offsets = [o for o in notice_offsets if type(o) is int and o > 0]
    items.append(CheckItem(
        "aviso_de_vencimento", "Cliente é avisado antes de pontos vencerem",
        required=True, ok=bool(offsets),
    ))
    items.append(CheckItem(
        "validade_generosa", "Validade de pelo menos 180 dias ou renovável",
        required=False,
        ok=rule.validity_days >= 180 or rule.expiry_policy == EXPIRY_ROLLING,
        detail="Vencimento é o principal motivo de abandono de programas.",
    ))
    return ClarityReport(items)
