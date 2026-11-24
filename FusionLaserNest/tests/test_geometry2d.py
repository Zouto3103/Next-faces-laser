import math
import random

import pytest

from FusionLaserNest.core.geometry2d import (
    LineSeg,
    ArcSeg,
    Contour,
    PartShape,
    convex_hull,
    is_chain_connected,
    min_area_rect_angle,
    order_segments_into_chain,
    orientation_candidates,
    place_part_shape,
    point_in_polygon,
    polygon_area,
    polygon_bbox,
    reverse_segment,
    rotate_point,
    segment_endpoints,
    transform_point,
)


def rect_polygon(w, h):
    return [(0, 0), (w, 0), (w, h), (0, h)]


def test_convex_hull_square():
    pts = [(0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0.5)]
    hull = convex_hull(pts)
    assert set(hull) == {(0, 0), (1, 0), (1, 1), (0, 1)}


def test_convex_hull_collinear_and_duplicates():
    pts = [(0, 0), (0, 0), (2, 0), (1, 0), (2, 2), (0, 2)]
    hull = convex_hull(pts)
    assert polygon_area(hull) == pytest.approx(4.0)


def test_polygon_area_rectangle():
    assert polygon_area(rect_polygon(3, 4)) == pytest.approx(12.0)


def test_rotate_point_90deg():
    p = rotate_point((1, 0), math.pi / 2)
    assert p[0] == pytest.approx(0.0, abs=1e-9)
    assert p[1] == pytest.approx(1.0, abs=1e-9)


def test_min_area_rect_angle_axis_aligned_square():
    hull = convex_hull(rect_polygon(5, 5))
    angle = min_area_rect_angle(hull)
    # Para um quadrado, qualquer multiplo de 90 graus e um minimo valido.
    normalized = angle % (math.pi / 2)
    assert normalized == pytest.approx(0.0, abs=1e-6) or normalized == pytest.approx(math.pi / 2, abs=1e-6)


def test_min_area_rect_angle_rotated_rectangle():
    # Retangulo 10x2 rotacionado 30 graus: o angulo minimo deve recuperar +-30 graus (mod 90).
    base = rect_polygon(10, 2)
    theta = math.radians(30)
    rotated = [rotate_point(p, theta) for p in base]
    hull = convex_hull(rotated)
    angle = min_area_rect_angle(hull)
    diff = abs((angle - theta + math.pi / 4) % (math.pi / 2) - math.pi / 4)
    assert diff < 1e-6


def test_orientation_candidates_modes():
    hull = convex_hull(rect_polygon(10, 4))

    none_orients = orientation_candidates(hull, "none")
    assert len(none_orients) == 1
    assert none_orients[0].width == pytest.approx(10.0)
    assert none_orients[0].height == pytest.approx(4.0)

    rect4 = orientation_candidates(hull, "rect4")
    assert len(rect4) == 4
    dims = sorted((round(o.width, 6), round(o.height, 6)) for o in rect4)
    assert dims[0] == (4.0, 10.0) or dims[0] == (10.0, 4.0)

    auto = orientation_candidates(hull, "auto")
    assert len(auto) == 2


def test_orientation_needs_90_rotation_to_fit_narrow_sheet():
    # Peca 10x2: nao cabe numa chapa 5x11 sem girar 90 graus.
    hull = convex_hull(rect_polygon(10, 2))
    orients = orientation_candidates(hull, "rect4")

    sheet_w, sheet_h = 5, 11
    fits_without_rotation = orients[0].width <= sheet_w and orients[0].height <= sheet_h
    assert not fits_without_rotation

    fits_rotated = any(o.width <= sheet_w and o.height <= sheet_h for o in orients)
    assert fits_rotated


def test_place_part_shape_moves_bbox_to_origin():
    outer = Contour(
        segments=[
            LineSeg((0, 0), (10, 0)),
            LineSeg((10, 0), (10, 4)),
            LineSeg((10, 4), (0, 4)),
            LineSeg((0, 4), (0, 0)),
        ],
        approx_polygon=rect_polygon(10, 4),
    )
    shape = PartShape(part_id="p1", outer=outer, holes=[])
    hull = convex_hull(outer.approx_polygon)
    orientation = orientation_candidates(hull, "none")[0]

    positioned = place_part_shape(shape, orientation, x=100.0, y=50.0, sheet_index=0)
    minx, miny, maxx, maxy = polygon_bbox(positioned.outer.approx_polygon)
    assert minx == pytest.approx(100.0)
    assert miny == pytest.approx(50.0)
    assert (maxx - minx) == pytest.approx(10.0)
    assert (maxy - miny) == pytest.approx(4.0)


def test_point_in_polygon():
    square = rect_polygon(10, 10)
    assert point_in_polygon((5, 5), square)
    assert not point_in_polygon((15, 5), square)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_property_random_rectangles_hull_area_matches(seed):
    rnd = random.Random(seed)
    w = rnd.uniform(1, 50)
    h = rnd.uniform(1, 50)
    theta = rnd.uniform(0, math.pi)
    base = rect_polygon(w, h)
    rotated = [rotate_point(p, theta) for p in base]
    hull = convex_hull(rotated)
    assert polygon_area(hull) == pytest.approx(w * h, rel=1e-6)

    angle = min_area_rect_angle(hull)
    check = [rotate_point(p, -angle) for p in hull]
    minx, miny, maxx, maxy = polygon_bbox(check)
    area = (maxx - minx) * (maxy - miny)
    assert area == pytest.approx(w * h, rel=1e-4)


def _chain_is_connected(chain, tol=1e-9):
    for i in range(len(chain)):
        _entry, exit_ = segment_endpoints(chain[i])
        next_entry, _next_exit = segment_endpoints(chain[(i + 1) % len(chain)])
        if math.hypot(exit_[0] - next_entry[0], exit_[1] - next_entry[1]) > tol:
            return False
    return True


def test_order_segments_into_chain_fixes_scrambled_order():
    # Quadrado 10x10 (0,0)->(10,0)->(10,10)->(0,10)->(0,0), com as arestas fora
    # de ordem e uma delas invertida -- exatamente o que BRepLoop.edges pode
    # devolver (so BRepLoop.coEdges e documentado como ordenado).
    bottom = LineSeg((0, 0), (10, 0))
    right = LineSeg((10, 0), (10, 10))
    top = LineSeg((0, 10), (10, 10))  # invertida em relacao ao sentido do loop
    left = LineSeg((0, 10), (0, 0))

    scrambled = [right, left, bottom, top]
    chain = order_segments_into_chain(scrambled)

    assert len(chain) == 4
    assert _chain_is_connected(chain)

    # O mesmo conjunto de arestas (sem direcao) deve estar presente.
    def undirected(seg):
        a, b = segment_endpoints(seg)
        return frozenset([a, b])

    assert {undirected(s) for s in chain} == {undirected(s) for s in scrambled}


def test_order_segments_into_chain_with_reversed_arc():
    # Meia-lua: uma linha reta de (10,0) a (-10,0) e um arco (semicirculo) de
    # (-10,0) de volta a (10,0). O arco e fornecido na direcao ERRADA
    # (start_angle/end_angle na ordem "natural" da curva, nao no sentido do loop).
    line = LineSeg((10, 0), (-10, 0))
    arc_natural = ArcSeg(center=(0, 0), radius=10, start_angle=0.0, end_angle=math.pi)  # (10,0) -> (-10,0)

    chain = order_segments_into_chain([line, arc_natural])
    assert len(chain) == 2
    assert _chain_is_connected(chain)

    # O arco precisou ser percorrido de (-10,0) para (10,0): deve ter sido marcado reversed.
    arc_in_chain = chain[1]
    assert isinstance(arc_in_chain, ArcSeg)
    assert arc_in_chain.reversed is True
    entry, exit_ = segment_endpoints(arc_in_chain)
    assert entry == pytest.approx((-10.0, 0.0))
    assert exit_ == pytest.approx((10.0, 0.0))
    # A forma fisica (center/radius/angulos) nao muda.
    assert arc_in_chain.center == arc_natural.center
    assert arc_in_chain.start_angle == arc_natural.start_angle
    assert arc_in_chain.end_angle == arc_natural.end_angle


def test_is_chain_connected_detects_gap():
    bottom = LineSeg((0, 0), (10, 0))
    right = LineSeg((10, 0), (10, 10))
    top = LineSeg((10, 10), (0, 10))
    left = LineSeg((0, 10), (0, 0))
    assert is_chain_connected([bottom, right, top, left])

    broken = LineSeg((10, 10), (99, 99))  # nao encosta em left
    assert not is_chain_connected([bottom, right, broken, left])


def test_reverse_segment_is_its_own_inverse():
    line = LineSeg((1, 2), (3, 4))
    assert reverse_segment(reverse_segment(line)) == line

    arc = ArcSeg(center=(0, 0), radius=5, start_angle=0.1, end_angle=1.5)
    twice = reverse_segment(reverse_segment(arc))
    assert twice.reversed == arc.reversed
    assert twice.start_angle == arc.start_angle
    assert twice.end_angle == arc.end_angle
