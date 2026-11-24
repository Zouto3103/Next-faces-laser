import random

import pytest

from FusionLaserNest.core.geometry2d import convex_hull, orientation_candidates
from FusionLaserNest.core.nesting import MaxRectsNester, PartForNesting


def rect_polygon(w, h):
    return [(0, 0), (w, 0), (w, h), (0, h)]


def make_part(part_id, w, h, mode="none"):
    hull = convex_hull(rect_polygon(w, h))
    orientations = orientation_candidates(hull, mode)
    return PartForNesting(part_id=part_id, orientations=orientations, area=w * h)


def placements_overlap(a, b, spacing=0.0):
    ax0, ay0 = a.x, a.y
    ax1, ay1 = a.x + a.orientation.width, a.y + a.orientation.height
    bx0, by0 = b.x, b.y
    bx1, by1 = b.x + b.orientation.width, b.y + b.orientation.height
    return not (ax1 + spacing <= bx0 + 1e-6 or bx1 + spacing <= ax0 + 1e-6 or ay1 + spacing <= by0 + 1e-6 or by1 + spacing <= ay0 + 1e-6)


def test_no_overlap_respecting_spacing_and_margin():
    rnd = random.Random(42)
    parts = [make_part(f"p{i}", rnd.uniform(20, 80), rnd.uniform(20, 80)) for i in range(12)]

    nester = MaxRectsNester()
    spacing = 3.0
    margin = 5.0
    sheet_w, sheet_h = 600.0, 400.0
    result = nester.pack(parts, sheet_w, sheet_h, spacing=spacing, margin=margin)

    by_sheet = {}
    for pl in result.placements:
        by_sheet.setdefault(pl.sheet_index, []).append(pl)

    for sheet_index, placements in by_sheet.items():
        usable_w = sheet_w - 2 * margin
        usable_h = sheet_h - 2 * margin
        for pl in placements:
            assert pl.x >= -1e-6
            assert pl.y >= -1e-6
            assert pl.x + pl.orientation.width <= usable_w + 1e-6
            assert pl.y + pl.orientation.height <= usable_h + 1e-6

        for i in range(len(placements)):
            for j in range(i + 1, len(placements)):
                assert not placements_overlap(placements[i], placements[j])


def test_rotation_resolves_case_that_only_fits_rotated():
    # Chapa 300 x 60 (mm), margem 5 -> area util 290 x 50.
    # Peca "em pe" 45 x 280: nessa orientacao a altura (280) nao cabe na chapa.
    # Girada 90 graus (280 x 45), a altura passa a ser 45 <= 50 e ela cabe.
    sheet_w, sheet_h = 300.0, 60.0

    part_no_rotation = make_part("A", 45, 280, mode="none")
    result_none = MaxRectsNester().pack([part_no_rotation], sheet_w, sheet_h, spacing=2.0, margin=5.0)
    assert result_none.unplaced == ["A"]

    part_with_rotation = make_part("A", 45, 280, mode="rect4")
    result_rect4 = MaxRectsNester().pack([part_with_rotation], sheet_w, sheet_h, spacing=2.0, margin=5.0)
    assert result_rect4.unplaced == []
    assert len(result_rect4.placements) == 1
    placed = result_rect4.placements[0]
    assert placed.orientation.width == pytest.approx(280.0)
    assert placed.orientation.height == pytest.approx(45.0)


def test_part_larger_than_sheet_is_unplaced_without_crashing():
    huge = make_part("huge", 900, 900, mode="rect4")
    normal = make_part("normal", 50, 50, mode="rect4")

    result = MaxRectsNester().pack([huge, normal], sheet_width=600, sheet_height=400, spacing=3.0, margin=5.0)

    assert "huge" in result.unplaced
    assert any(p.part_id == "normal" for p in result.placements)
    assert result.sheet_count >= 1


def test_multiple_sheets_opened_when_needed():
    parts = [make_part(f"sq{i}", 200, 200, mode="none") for i in range(6)]
    result = MaxRectsNester().pack(parts, sheet_width=600, sheet_height=400, spacing=3.0, margin=5.0)

    assert len(result.placements) == 6
    assert result.sheet_count >= 2
    for sheet in result.sheets:
        assert 0.0 <= sheet.utilization <= 1.0


def test_multi_strategy_search_beats_single_area_only_pass():
    # Caso real (achado por busca aleatoria) onde ordenar so por area
    # decrescente (o antigo comportamento de v1, um unico passe guloso) usa 6
    # chapas, enquanto tentar varias ordenacoes e ficar com a melhor resolve
    # com 5. Existe para responder a duvida "sera que ele realmente faz
    # nesting, ou so poe cada peca em qualquer lugar?": MaxRectsNester.pack
    # tenta de fato varias estrategias e escolhe a que aloca mais pecas, usa
    # menos chapas e aproveita melhor a chapa (ver core/nesting.py, docstring
    # de MaxRectsNester).
    dims = [
        (76.66, 74.86), (39.13, 74.14), (74.55, 17.0), (54.05, 60.65),
        (30.75, 62.02), (72.69, 78.13), (45.06, 77.7), (45.54, 73.71),
        (23.29, 29.89), (78.14, 44.96), (75.86, 37.53), (69.73, 43.62),
    ]
    parts = [make_part(f"p{i}", w, h, mode="none") for i, (w, h) in enumerate(dims)]
    sheet_w, sheet_h, spacing, margin = 120.0, 120.0, 2.0, 3.0

    area_order = sorted(parts, key=lambda p: p.area, reverse=True)
    area_only_result = MaxRectsNester._pack_ordered(
        area_order, sheet_w - 2 * margin, sheet_h - 2 * margin, spacing, margin, 200
    )
    best_result = MaxRectsNester().pack(parts, sheet_w, sheet_h, spacing=spacing, margin=margin)

    assert area_only_result.unplaced == []
    assert best_result.unplaced == []
    assert best_result.sheet_count < area_only_result.sheet_count
    assert MaxRectsNester._score(best_result) < MaxRectsNester._score(area_only_result)


def test_pack_result_is_never_worse_than_any_single_strategy():
    rnd = random.Random(7)
    parts = [make_part(f"p{i}", rnd.uniform(10, 80), rnd.uniform(10, 80), mode="none") for i in range(10)]
    sheet_w, sheet_h, spacing, margin = 150.0, 150.0, 2.0, 4.0

    best_result = MaxRectsNester().pack(parts, sheet_w, sheet_h, spacing=spacing, margin=margin)
    best_score = MaxRectsNester._score(best_result)

    for key in ("area", "max_dim", "perimeter", "width", "height", "min_dim"):
        from FusionLaserNest.core.nesting import _first_orientation_metric

        ordered = sorted(parts, key=lambda p: _first_orientation_metric(p, key), reverse=True)
        single = MaxRectsNester._pack_ordered(ordered, sheet_w - 2 * margin, sheet_h - 2 * margin, spacing, margin, 200)
        assert best_score <= MaxRectsNester._score(single)
