"""Exportacao de cada chapa: DXF (via ExportManager, API em preview) + SVG
(escrito por nos mesmos, core/svg_writer.py).
"""
from __future__ import annotations

import os
from typing import List

import adsk.core
import adsk.fusion

from ..core.geometry2d import PositionedPart
from ..core.svg_writer import build_sheet_svg


class DxfExportError(RuntimeError):
    pass


def export_dxf(design: "adsk.fusion.Design", sketch: "adsk.fusion.Sketch", filepath: str) -> None:
    """Exporta um esboco para DXF em mm, sem geometria de construcao nem pontos.

    ATENCAO: ExportManager.createDXFSketchExportOptions e uma API em PREVIEW
    (introduzida em jan/2025). Se a Autodesk mudar sua assinatura em uma versao
    futura do Fusion, este e o unico ponto do add-in que precisa ser ajustado.
    """
    export_mgr = design.exportManager
    try:
        options = export_mgr.createDXFSketchExportOptions(filepath, sketch)
        if options is None:
            raise DxfExportError("Fusion nao conseguiu criar as opcoes de exportacao DXF (retornou None).")

        options.units = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
        options.isConstructionExported = False
        options.isPointsExported = False
        options.isProjectedGeometryExported = False

        ok = export_mgr.execute(options)
        if not ok:
            raise DxfExportError(f"ExportManager.execute retornou False para '{filepath}'.")
    except AttributeError as exc:
        raise DxfExportError(
            "A API de exportacao de DXF (ExportManager.createDXFSketchExportOptions) "
            "parece ter mudado nesta versao do Fusion. Esta funcionalidade e uma "
            "API em preview da Autodesk (ver README, secao Decisoes/Riscos)."
        ) from exc


def export_svg(sheet_width_mm: float, sheet_height_mm: float, parts: List[PositionedPart], filepath: str) -> None:
    svg_text = build_sheet_svg(sheet_width_mm, sheet_height_mm, parts)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg_text)


def sheet_filepaths(output_folder: str, base_name: str, sheet_index: int) -> "tuple[str, str]":
    stem = f"{base_name}_chapa{sheet_index + 1:02d}"
    dxf_path = os.path.join(output_folder, stem + ".dxf")
    svg_path = os.path.join(output_folder, stem + ".svg")
    return dxf_path, svg_path
