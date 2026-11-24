import math
import re
import xml.etree.ElementTree as ET

import pytest

from FusionLaserNest.core.geometry2d import (
    ArcSeg,
    CircleSeg,
    Contour,
    LineSeg,
    PositionedPart,
    point_in_polygon,
)
from FusionLaserNest.core.svg_writer import build_sheet_svg


def rect_contour(w, h, is_outer=True):
    poly = [(0, 0), (w, 0), (w, h), (0, h)]
    segs = [
        LineSeg((0, 0), (w, 0)),
        LineSeg((w, 0), (w, h)),
        LineSeg((w, h), (0, h)),
        LineSeg((0, h), (0, 0)),
    ]
    return Contour(segments=segs, approx_polygon=poly, is_outer=is_outer)


def circle_hole_contour(cx, cy, r):
    n = 32
    import math

    poly = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return Contour(segments=[CircleSeg(center=(cx, cy), radius=r)], approx_polygon=poly, is_outer=False)


def test_svg_is_valid_xml_and_viewbox_in_mm():
    sheet_w, sheet_h = 600.0, 400.0
    outer = rect_contour(100, 60)
    hole = circle_hole_contour(50, 30, 10)
    part = PositionedPart(part_id="peca1", outer=outer, holes=[hole], sheet_index=0)

    svg = build_sheet_svg(sheet_w, sheet_h, [part])

    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.attrib["viewBox"] == f"0 0 {sheet_w:.0f} {sheet_h:.0f}"
    assert root.attrib["width"] == f"{sheet_w:.0f}mm"
    assert root.attrib["height"] == f"{sheet_h:.0f}mm"


def test_all_paths_are_closed():
    outer = rect_contour(100, 60)
    hole = circle_hole_contour(50, 30, 10)
    part = PositionedPart(part_id="peca1", outer=outer, holes=[hole], sheet_index=0)

    svg = build_sheet_svg(600, 400, [part])
    root = ET.fromstring(svg)

    ns = {"svg": "http://www.w3.org/2000/svg"}
    paths = root.findall(".//svg:path", ns)
    assert len(paths) == 2  # 1 contorno externo + 1 furo
    for p in paths:
        d = p.attrib["d"]
        assert d.strip().startswith("M")
        assert d.strip().endswith("Z")


def test_hole_center_is_inside_outer_contour():
    outer = rect_contour(100, 60)
    hole = circle_hole_contour(50, 30, 10)

    assert point_in_polygon((50, 30), outer.approx_polygon)
    for p in hole.approx_polygon:
        assert point_in_polygon(p, outer.approx_polygon)


def test_svg_path_is_correct_even_with_segments_scrambled_and_reversed():
    # Reproduz o bug real: BRepLoop.edges (ou qualquer fonte) pode devolver as
    # arestas fora de ordem e com direcao misturada. O SVG precisa desenhar a
    # forma certa mesmo assim, ja que cada segmento e um sub-path proprio com
    # coordenadas absolutas (nao depende de encadeamento).
    bottom = LineSeg((0, 0), (10, 0))
    right = LineSeg((10, 0), (10, 5))
    top = LineSeg((0, 5), (10, 5))  # direcao invertida em relacao ao sentido do loop
    left = LineSeg((0, 5), (0, 0))  # direcao invertida tambem

    scrambled = Contour(segments=[right, left, bottom, top], approx_polygon=[(0, 0), (10, 0), (10, 5), (0, 5)])
    part = PositionedPart(part_id="scrambled", outer=scrambled, holes=[], sheet_index=0)

    svg = build_sheet_svg(600, 400, [part])
    root = ET.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    path = root.find(".//svg:g[@id='outer-contours']/svg:path", ns)
    d = path.attrib["d"]

    # 4 segmentos = 4 subpaths "M ... L ..." dentro do mesmo atributo "d".
    assert d.count("M") == 4

    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    xs, ys = nums[0::2], nums[1::2]
    assert min(xs) == pytest.approx(0.0)
    assert max(xs) == pytest.approx(10.0)
    # Y foi invertido (sheet_height=400): o retangulo de altura 5 fica entre
    # y=395 e y=400 no espaco do SVG.
    assert min(ys) == pytest.approx(395.0)
    assert max(ys) == pytest.approx(400.0)


def test_svg_arc_shape_independent_of_reversed_flag():
    # O mesmo arco fisico, uma vez normal e outra marcado reversed=True, deve
    # produzir o MESMO comando SVG (reversed so importa para encadeamento).
    arc = ArcSeg(center=(0, 0), radius=10, start_angle=0.0, end_angle=math.pi / 2)
    arc_rev = ArcSeg(center=(0, 0), radius=10, start_angle=0.0, end_angle=math.pi / 2, reversed=True)

    outer = Contour(segments=[arc], approx_polygon=[(10, 0), (0, 10)])
    outer_rev = Contour(segments=[arc_rev], approx_polygon=[(10, 0), (0, 10)])

    part = PositionedPart(part_id="p", outer=outer, holes=[], sheet_index=0)
    part_rev = PositionedPart(part_id="p", outer=outer_rev, holes=[], sheet_index=0)

    svg = build_sheet_svg(600, 400, [part])
    svg_rev = build_sheet_svg(600, 400, [part_rev])

    def path_d(svg_text):
        root = ET.fromstring(svg_text)
        ns = {"svg": "http://www.w3.org/2000/svg"}
        return root.find(".//svg:g[@id='outer-contours']/svg:path", ns).attrib["d"]

    assert path_d(svg) == path_d(svg_rev)


def _arc_path_d(arc: ArcSeg, sheet_height=400.0, sheet_width=600.0):
    outer = Contour(segments=[arc], approx_polygon=[arc.start_point, arc.end_point])
    part = PositionedPart(part_id="p", outer=outer, holes=[], sheet_index=0)
    svg = build_sheet_svg(sheet_width, sheet_height, [part])
    root = ET.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    return root.find(".//svg:g[@id='outer-contours']/svg:path", ns).attrib["d"]


def _parse_arc_flags(d: str):
    # "M x y A rx ry rot large-arc sweep ex ey"
    m = re.search(r"A\s+[\d.]+\s+[\d.]+\s+\d+\s+(\d)\s+(\d)\s+", d)
    assert m, d
    return int(m.group(1)), int(m.group(2))


def test_svg_arc_bulges_the_correct_way_not_inverted():
    # Bug real: o arco conectava certo nas pontas mas curvava para o lado
    # ERRADO (filete "para dentro" em vez de "para fora"). Caso simples e
    # facil de verificar a mao: quarto de circulo no primeiro quadrante, de
    # (10,0) a (0,10) ao redor da origem -- o arco verdadeiro passa por
    # (7.07,7.07), "afastado" da origem (bulge para fora), nunca "para dentro"
    # (o que passaria perto da origem, por ex. por algo como (2,2)).
    arc = ArcSeg(center=(0, 0), radius=10, start_angle=0.0, end_angle=math.pi / 2)
    d = _arc_path_d(arc, sheet_height=20.0, sheet_width=20.0)
    large_arc, sweep_flag = _parse_arc_flags(d)

    # Confirmado por dois metodos independentes (ver comentario em
    # core/svg_writer.py::_arc_svg_flags): para este caso o flag correto e
    # sweep=0 (visualmente CCW), large-arc=0 (arco menor, 90 graus).
    assert large_arc == 0
    assert sweep_flag == 0


def test_svg_arc_matches_real_fillet_from_reported_bug():
    # Dados reais do DXF/SVG que o usuario mandou (fillet de raio 10mm,
    # centro (15,15), pontos (5,15) e (15,5), chapa 400mm de altura) --
    # trava a correcao exata que resolveu o bug relatado.
    arc = ArcSeg(center=(15, 15), radius=10, start_angle=math.pi, end_angle=math.pi + math.pi / 2)
    d = _arc_path_d(arc, sheet_height=400.0)
    large_arc, sweep_flag = _parse_arc_flags(d)
    assert (large_arc, sweep_flag) == (0, 0)

    # A outra ponta da mesma peca (centro (340,15), pontos (340,5) e (350,15)
    # -- confirmado batendo com a entidade ARC do DXF real, startAngle=-90,
    # endAngle=0) tambem precisa do mesmo par de flags -- o bug antigo usava
    # sweep=1 fixo nos dois casos, o que so por coincidencia poderia acertar
    # um dos dois.
    arc2 = ArcSeg(center=(340, 15), radius=10, start_angle=-math.pi / 2, end_angle=0.0)
    d2 = _arc_path_d(arc2, sheet_height=400.0)
    large_arc2, sweep_flag2 = _parse_arc_flags(d2)
    assert (large_arc2, sweep_flag2) == (0, 0)


def test_svg_has_no_fill_and_hairline_stroke():
    outer = rect_contour(100, 60)
    part = PositionedPart(part_id="peca1", outer=outer, holes=[], sheet_index=0)
    svg = build_sheet_svg(600, 400, [part])

    assert 'fill="none"' in svg
    assert 'stroke-width="0.1"' in svg
    assert "#0000FF" in svg  # contorno externo azul
    assert "#999999" in svg  # chapa (nao-corte)
