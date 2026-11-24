from FusionLaserNest.core.nesting import PackResult, Placement, SheetResult
from FusionLaserNest.core.geometry2d import Orientation
from FusionLaserNest.core.report import build_report_text


def _orientation(w, h):
    return Orientation(angle_rad=0.0, width=w, height=h, offset=(0.0, 0.0))


def test_report_all_placed_no_warning():
    result = PackResult(
        placements=[Placement(part_id="a", sheet_index=0, x=0, y=0, orientation=_orientation(10, 10))],
        unplaced=[],
        sheets=[SheetResult(index=0, usable_width=100, usable_height=100, used_area=100)],
    )
    text = build_report_text(result, total_parts=1)
    assert "Pecas alocadas: 1 de 1" in text
    assert "Nenhuma peca ficou de fora." in text
    assert "ATENCAO" not in text


def test_report_warns_clearly_about_unplaced_pieces():
    result = PackResult(
        placements=[Placement(part_id="a", sheet_index=0, x=0, y=0, orientation=_orientation(10, 10))],
        unplaced=["b#1", "b#2"],
        sheets=[SheetResult(index=0, usable_width=100, usable_height=100, used_area=100)],
    )
    text = build_report_text(result, total_parts=3)
    assert "Pecas alocadas: 1 de 3" in text
    assert "ATENCAO" in text
    assert "2 peca(s)" in text
    assert "b#1" in text
    assert "b#2" in text


def test_report_lists_sheet_utilization():
    result = PackResult(
        placements=[],
        unplaced=[],
        sheets=[
            SheetResult(index=0, usable_width=100, usable_height=100, used_area=5000),
            SheetResult(index=1, usable_width=100, usable_height=100, used_area=2500),
        ],
    )
    text = build_report_text(result, total_parts=0)
    assert "Numero de chapas usadas: 2" in text
    assert "Chapa 1: aproveitamento 50.0%" in text
    assert "Chapa 2: aproveitamento 25.0%" in text
