import re
import xml.etree.ElementTree as ET

import pytest

from FusionLaserNest.core.geometry2d import Contour, LineSeg, PositionedPart
from FusionLaserNest.core.svg_writer import build_sheet_svg
from FusionLaserNest.core.units import cm_to_mm, mm_to_cm


def test_cm_to_mm_and_back():
    assert cm_to_mm(1.0) == pytest.approx(10.0)
    assert cm_to_mm(10.0) == pytest.approx(100.0)
    assert mm_to_cm(100.0) == pytest.approx(10.0)
    assert mm_to_cm(cm_to_mm(5.0)) == pytest.approx(5.0)


def _path_bbox(d: str):
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    xs = nums[0::2]
    ys = nums[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def test_square_of_100mm_from_cm_comes_out_as_100mm_in_svg():
    side_cm = 10.0
    side_mm = cm_to_mm(side_cm)
    assert side_mm == pytest.approx(100.0)

    poly = [(0, 0), (side_mm, 0), (side_mm, side_mm), (0, side_mm)]
    segs = [
        LineSeg((0, 0), (side_mm, 0)),
        LineSeg((side_mm, 0), (side_mm, side_mm)),
        LineSeg((side_mm, side_mm), (0, side_mm)),
        LineSeg((0, side_mm), (0, 0)),
    ]
    outer = Contour(segments=segs, approx_polygon=poly)
    part = PositionedPart(part_id="quadrado", outer=outer, holes=[], sheet_index=0)

    svg = build_sheet_svg(600.0, 400.0, [part])
    root = ET.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    path = root.find(".//svg:g[@id='outer-contours']/svg:path", ns)

    minx, miny, maxx, maxy = _path_bbox(path.attrib["d"])
    assert (maxx - minx) == pytest.approx(100.0, abs=1e-3)
    assert (maxy - miny) == pytest.approx(100.0, abs=1e-3)
