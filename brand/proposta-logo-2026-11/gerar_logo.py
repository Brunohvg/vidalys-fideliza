"""Gera a proposta de logo do Vidalys Fideliza (SVG, texto convertido em curvas).

Uso: python gerar_logo.py <pasta_saida>
Opção A — "Sacola-órbita": o conceito aprovado (sacola + estrela + órbita), redesenhado
          plano, com 3 cores, para ser legível em 16 px.
Opção B — "Ciclo": a órbita vira o símbolo (anel aberto com seta = voltar), estrela no
          centro = recompensa, ponto laranja = o cliente percorrendo o ciclo.
Texto: Inter Display (SIL OFL) convertida em curvas. Troque por Manrope se tiver o arquivo.
"""
import math
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
FONT_DIR = Path("/usr/share/fonts/opentype/inter")

INK, PRIMARY, PURPLE_500, DEEP = "#3B1E82", "#6A3DF0", "#8B43F6", "#24113F"
GOLD, ORANGE, WHITE, LAVENDER = "#FFC857", "#FF8A3D", "#FFFFFF", "#EDE7FF"


def text_path(text, font_file, size, x, y, tracking=0.0):
    """Converte texto em <path d> (sem depender de fonte instalada no visitante)."""
    font = TTFont(FONT_DIR / font_file)
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    scale = size / upm
    pen = SVGPathPen(glyphs)
    cursor = x
    for ch in text:
        name = cmap[ord(ch)]
        glyph = glyphs[name]
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, cursor, y)))
        cursor += glyph.width * scale + tracking * size
    return pen.getCommands(), cursor - x


def star(cx, cy, outer, inner, points=5, rotation=-90):
    pts = []
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = math.radians(rotation + i * 180 / points)
        pts.append(f"{cx + r * math.cos(a):.2f},{cy + r * math.sin(a):.2f}")
    return "M" + " L".join(pts) + " Z"


# ---------- Opção A: sacola + estrela + órbita, plano ----------
def mark_a(dark=False, orbit=True):
    handle = LAVENDER if dark else INK
    parts = []
    if orbit:  # órbita atrás, saindo pela esquerda e voltando pela direita
        parts.append(f'<path d="M7 43 C 3 55, 30 62, 52 50 C 58 46.5, 61 42, 60 38" fill="none" '
                     f'stroke="{ORANGE}" stroke-width="3.6" stroke-linecap="round"/>')
    parts.append(f'<path d="M24 25 V19.5 a8 8 0 0 1 16 0 V25" fill="none" stroke="{handle}" '
                 f'stroke-width="4.4" stroke-linecap="round"/>')
    parts.append(f'<path d="M16.5 24 H47.5 Q51.6 24 52 28.1 L54.3 49.6 Q54.9 55.5 49 55.5 H15 '
                 f'Q9.1 55.5 9.7 49.6 L12 28.1 Q12.4 24 16.5 24 Z" fill="{PRIMARY}"/>')
    parts.append(f'<path d="{star(32, 40.2, 10.2, 4.4)}" fill="{GOLD}" stroke="{GOLD}" '
                 f'stroke-width="1.6" stroke-linejoin="round"/>')
    if orbit:  # trecho da órbita passando NA FRENTE da sacola
        parts.append(f'<path d="M14.5 51.3 C 24 55.4, 38 55.6, 52 50" fill="none" stroke="{ORANGE}" '
                     f'stroke-width="3.6" stroke-linecap="round"/>')
    return "".join(parts)


# ---------- Opção B: ciclo (anel aberto com seta) + estrela ----------
def mark_b(dark=False):
    ring = LAVENDER if dark else PRIMARY
    r, cx, cy = 23, 32, 32
    start, end = math.radians(-58), math.radians(262)  # abertura no alto à direita
    x1, y1 = cx + r * math.cos(start), cy + r * math.sin(start)
    x2, y2 = cx + r * math.cos(end), cy + r * math.sin(end)
    arc = (f'<path d="M{x1:.2f} {y1:.2f} A{r} {r} 0 1 1 {x2:.2f} {y2:.2f}" fill="none" '
           f'stroke="{ring}" stroke-width="7" stroke-linecap="round"/>')
    # ponta de seta no fim do arco (sentido horário = "voltar")
    ang = end + math.pi / 2
    tip = (x2 + 6.5 * math.cos(ang), y2 + 6.5 * math.sin(ang))
    l = (x2 + 6.2 * math.cos(end), y2 + 6.2 * math.sin(end))
    rr = (x2 - 6.2 * math.cos(end), y2 - 6.2 * math.sin(end))
    arrow = (f'<path d="M{l[0]:.2f} {l[1]:.2f} L{tip[0]:.2f} {tip[1]:.2f} L{rr[0]:.2f} {rr[1]:.2f} Z" '
             f'fill="{ring}" stroke="{ring}" stroke-width="2" stroke-linejoin="round"/>')
    dot_a = math.radians(140)
    dot = (f'<circle cx="{cx + r * math.cos(dot_a):.2f}" cy="{cy + r * math.sin(dot_a):.2f}" r="6" '
           f'fill="{ORANGE}" stroke="{DEEP if dark else WHITE}" stroke-width="2.5"/>')
    st = (f'<path d="{star(cx, cy + 0.8, 11.5, 5)}" fill="{GOLD}" stroke="{GOLD}" '
          f'stroke-width="1.8" stroke-linejoin="round"/>')
    return arc + arrow + dot + st


def svg(viewbox, body, label="Vidalys Fideliza"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" role="img" '
            f'aria-label="{label}">{body}</svg>\n')


def app_icon(mark_fn):
    """Ícone quadrado (favicon/app): fundo roxo escuro, símbolo claro."""
    bg = (f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{INK}"/>'
          f'<stop offset="1" stop-color="{PRIMARY}"/></linearGradient></defs>'
          f'<rect width="64" height="64" rx="15" fill="url(#g)"/>')
    return bg + f'<g transform="translate(5.5 5.5) scale(.83)">{mark_fn(True)}</g>'


def lockup(mark_body, dark=False):
    """Logo horizontal: símbolo + 'Vidalys' pequeno + 'Fideliza' forte, em curvas."""
    top, top_w = text_path("Vidalys", "InterDisplay-SemiBold.otf", 19, 76, 27, tracking=-0.01)
    main, main_w = text_path("Fideliza", "InterDisplay-ExtraBold.otf", 34, 75, 57, tracking=-0.035)
    width = 75 + max(top_w, main_w) + 4
    c_top = LAVENDER if dark else INK
    c_main = WHITE if dark else PRIMARY
    body = (f'<g>{mark_body}</g><path d="{top}" fill="{c_top}"/><path d="{main}" fill="{c_main}"/>')
    return svg(f"0 0 {width:.1f} 64", body), width


files = {
    "opcao-a-simbolo.svg": svg("0 0 64 64", mark_a()),
    "opcao-a-simbolo-branco.svg": svg("0 0 64 64", mark_a(dark=True)),
    "opcao-a-favicon.svg": svg("0 0 64 64", app_icon(lambda d: mark_a(d, orbit=False))),
    "opcao-b-simbolo.svg": svg("0 0 64 64", mark_b()),
    "opcao-b-simbolo-branco.svg": svg("0 0 64 64", mark_b(dark=True)),
    "opcao-b-favicon.svg": svg("0 0 64 64", app_icon(mark_b)),
}
files["opcao-a-logo.svg"], _ = lockup(mark_a())
files["opcao-a-logo-branco.svg"], _ = lockup(mark_a(dark=True), dark=True)
files["opcao-b-logo.svg"], _ = lockup(mark_b())
files["opcao-b-logo-branco.svg"], _ = lockup(mark_b(dark=True), dark=True)
for name, content in files.items():
    (OUT / name).write_text(content, encoding="utf-8")
print("\n".join(sorted(files)))
