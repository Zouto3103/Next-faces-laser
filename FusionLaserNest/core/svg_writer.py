"""Escritor de SVG vetorial (mm) para LightBurn/RDWorks.

Sem dependencias externas (so biblioteca padrao). Nao importa adsk.*.

Convencoes:
- Unidades: mm (atributo width/height do <svg> e viewBox, tudo em mm).
- Eixo Y invertido: nossa geometria interna usa Y crescendo para cima
  (matematico); SVG usa Y crescendo para baixo. Toda coordenada e espelhada
  verticalmente (`y_svg = sheet_height_mm - y_math`) ao escrever o path.
- Sem preenchimento (fill="none"), traco hairline (0.1mm).
- Cores por camada: contorno externo azul (#0000FF), furos vermelho (#FF0000),
  contorno da chapa cinza tracejado (#999999), como geometria de nao-corte.
- Arcos -> comando "A"; splines -> polilinha (aproximacao ja calculada por
  quem gerou o SplineSeg, tolerancia <= 0.05 mm) representada como "L"
  encadeados (uma polilinha e uma aproximacao Bezier-por-partes valida para o
  laser, que so precisa de segmentos retos curtos).
- Flags large-arc/sweep do comando "A": NUNCA supostos por uma regra fixa
  (ver `_arc_svg_flags`) -- um raciocinio anterior sobre como a inversao do
  eixo Y afeta a quiralidade do arco (CCW vira CW?) se provou errado num
  caso real (o filete saia curvando "para dentro" em vez de "para fora",
  apesar de conectar certo nas pontas). Em vez disso, os flags sao MEDIDOS
  diretamente nas coordenadas ja no espaco SVG a cada arco.
- Cada aresta (segmento) do contorno e desenhada como um SUB-PATH PROPRIO
  ("M inicio ... fim", um por segmento, todos concatenados no mesmo atributo
  "d" -- SVG aceita varios "M" num so "d"). Decisao deliberada: cada segmento
  ja tem coordenadas absolutas corretas (vem de geometria B-Rep exata,
  nivelada e posicionada), entao desenha-lo sozinho e sempre correto,
  independente de QUALQUER ordem ou direcao em que os segmentos apareçam na
  lista. Isso elimina de vez os bugs de "ziguezague" que apareciam quando se
  tentava desenhar os segmentos como uma unica cadeia continua assumindo que
  um terminava exatamente onde o proximo comecava -- em pecas com muitas
  arestas bem proximas (dentes de encaixe apertados), mesmo depois de corrigir
  a ordem de extracao (BRepLoop.coEdges + isOpposedToEdge, com
  order_segments_into_chain como rede de seguranca -- ver face_to_2d.py),
  ainda sobravam alguns segmentos mal encadeados. Como os segmentos coincidem
  exatamente nas extremidades compartilhadas (topologia B-Rep valida), varios
  sub-paths desenhados lado a lado formam visualmente o mesmo contorno fechado
  que uma cadeia continua formaria -- sem depender de acertar a ordem.
"""
from __future__ import annotations

import math
from typing import List

from .geometry2d import ArcSeg, CircleSeg, Contour, LineSeg, PositionedPart, SplineSeg

STROKE_WIDTH_MM = 0.1
COLOR_OUTER = "#0000FF"
COLOR_HOLE = "#FF0000"
COLOR_SHEET = "#999999"

SVG_NS = "http://www.w3.org/2000/svg"


def _flip_y(y: float, sheet_height: float) -> float:
    return sheet_height - y


def _fmt(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") if "." in f"{v:.4f}" else f"{v:.4f}"


def _arc_svg_flags(start_svg, end_svg, center_svg, true_sweep: float):
    """Decide os flags large-arc/sweep do comando SVG "A" MEDINDO diretamente
    nas coordenadas ja invertidas (espaco SVG), em vez de supor como a
    inversao do eixo Y afeta o sentido do arco.

    Bug real encontrado ao testar (raio saindo "para dentro" em vez de "para
    fora"): a versao anterior fixava `sweep-flag=1` com base num raciocinio
    sobre CCW-vira-CW-apos-inverter-Y que se provou errado nalgum caso. Em vez
    de tentar acertar esse raciocinio abstrato de novo, medimos: calculamos o
    angulo de start/end em relacao ao centro DIRETO no espaco SVG (o mesmo
    espaco onde o comando "A" vai ser interpretado), comparamos com a
    magnitude verdadeira do arco (`true_sweep`, ja validada na extracao -- ver
    face_to_2d.py::_arc_segment_from_arc3d) e escolhemos o flag que da exatamente
    essa magnitude. Isso elimina a dependencia de acertar a teoria de
    quiralidade e so confia em medir o que esta na nossa frente.
    """
    ang_start = math.atan2(start_svg[1] - center_svg[1], start_svg[0] - center_svg[0])
    ang_end = math.atan2(end_svg[1] - center_svg[1], end_svg[0] - center_svg[0])
    positive_sweep = (ang_end - ang_start) % (2.0 * math.pi)  # sweep-flag=1, per SVG spec

    if abs(positive_sweep - true_sweep) <= abs((2.0 * math.pi - positive_sweep) - true_sweep):
        sweep_flag = 1
        actual_sweep = positive_sweep
    else:
        sweep_flag = 0
        actual_sweep = (2.0 * math.pi) - positive_sweep

    large_arc = 1 if actual_sweep > math.pi + 1e-9 else 0
    return large_arc, sweep_flag


def _contour_to_path_d(contour: Contour, sheet_height: float) -> str:
    if not contour.segments:
        return ""

    def pt(p):
        return (p[0], _flip_y(p[1], sheet_height))

    subpaths: List[str] = []

    for seg in contour.segments:
        if isinstance(seg, LineSeg):
            p0, p1 = pt(seg.p0), pt(seg.p1)
            subpaths.append(f"M {_fmt(p0[0])} {_fmt(p0[1])} L {_fmt(p1[0])} {_fmt(p1[1])}")
        elif isinstance(seg, ArcSeg):
            start, end, center_svg = pt(seg.start_point), pt(seg.end_point), pt(seg.center)
            large_arc, sweep_flag = _arc_svg_flags(start, end, center_svg, seg.sweep)
            subpaths.append(
                f"M {_fmt(start[0])} {_fmt(start[1])} "
                f"A {_fmt(seg.radius)} {_fmt(seg.radius)} 0 {large_arc} {sweep_flag} {_fmt(end[0])} {_fmt(end[1])}"
            )
        elif isinstance(seg, CircleSeg):
            cx, cy = seg.center
            r = seg.radius
            p_start = pt((cx + r, cy))
            p_mid = pt((cx - r, cy))
            subpaths.append(
                f"M {_fmt(p_start[0])} {_fmt(p_start[1])} "
                f"A {_fmt(r)} {_fmt(r)} 0 0 1 {_fmt(p_mid[0])} {_fmt(p_mid[1])} "
                f"A {_fmt(r)} {_fmt(r)} 0 0 1 {_fmt(p_start[0])} {_fmt(p_start[1])}"
            )
        elif isinstance(seg, SplineSeg):
            pts = [pt(p) for p in seg.points]
            cmd = [f"M {_fmt(pts[0][0])} {_fmt(pts[0][1])}"]
            for p in pts[1:]:
                cmd.append(f"L {_fmt(p[0])} {_fmt(p[1])}")
            subpaths.append(" ".join(cmd))
        else:
            raise TypeError(f"Segmento desconhecido: {type(seg)!r}")

    return " ".join(subpaths) + " Z"


def build_sheet_svg(sheet_width_mm: float, sheet_height_mm: float, parts: List[PositionedPart]) -> str:
    """Gera o conteudo do SVG (string) para uma chapa."""
    lines: List[str] = []
    lines.append(
        f'<svg xmlns="{SVG_NS}" width="{_fmt(sheet_width_mm)}mm" height="{_fmt(sheet_height_mm)}mm" '
        f'viewBox="0 0 {_fmt(sheet_width_mm)} {_fmt(sheet_height_mm)}">'
    )

    # Contorno da chapa: nao-corte, cinza tracejado.
    lines.append(
        f'<g id="sheet-outline" stroke="{COLOR_SHEET}" stroke-width="{STROKE_WIDTH_MM}" '
        f'stroke-dasharray="2,1" fill="none">'
    )
    lines.append(f'<rect x="0" y="0" width="{_fmt(sheet_width_mm)}" height="{_fmt(sheet_height_mm)}" />')
    lines.append("</g>")

    lines.append(f'<g id="outer-contours" stroke="{COLOR_OUTER}" stroke-width="{STROKE_WIDTH_MM}" fill="none">')
    for part in parts:
        d = _contour_to_path_d(part.outer, sheet_height_mm)
        lines.append(f'<path id="{_escape(part.part_id)}-outer" d="{d}" />')
    lines.append("</g>")

    lines.append(f'<g id="hole-contours" stroke="{COLOR_HOLE}" stroke-width="{STROKE_WIDTH_MM}" fill="none">')
    for part in parts:
        for i, hole in enumerate(part.holes):
            d = _contour_to_path_d(hole, sheet_height_mm)
            lines.append(f'<path id="{_escape(part.part_id)}-hole-{i}" d="{d}" />')
    lines.append("</g>")

    lines.append("</svg>")
    return "\n".join(lines)


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
