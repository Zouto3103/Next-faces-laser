"""Comando de auto-teste: cria um documento novo com 4 pecas de teste
(ver README, secao de checklist de aceitacao):
  1. Retangulo com furo circular E cantos arredondados (fillet -- unica peca
     com um ARCO PARCIAL, ao contrario do furo/peca 3 que sao circulos inteiros).
  2. Peca com "dentes de encaixe" (perfil em zigue-zague, so linhas retas).
  3. Peca circular.
  4. Peca extrudada num plano diferente do XY (testa o nivelamento).

Cada peca e um BRepBody independente na raiz do documento novo, com espessura,
pronta para o usuario selecionar a face de maior area de cada uma e rodar o
comando "Nest Faces (Laser)". Cada peca e desenhada ja deslocada (offset_x,
offset_y) para nao se sobrepor as outras -- assim evitamos depender da API de
Move Feature, que nao e necessaria aqui.
"""
from __future__ import annotations

import adsk.core
import adsk.fusion

THICKNESS_CM = 0.5


def _extrude_profile(component: "adsk.fusion.Component", sketch: "adsk.fusion.Sketch", profile_index: int = 0) -> "adsk.fusion.BRepBody":
    prof = sketch.profiles.item(profile_index)
    extrudes = component.features.extrudeFeatures
    ext_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    distance = adsk.core.ValueInput.createByReal(THICKNESS_CM)
    ext_input.setDistanceExtent(False, distance)
    ext = extrudes.add(ext_input)
    return ext.bodies.item(0)


def _rectangle_with_hole(component: "adsk.fusion.Component", offset_x: float, offset_y: float) -> "adsk.fusion.BRepBody":
    """Retangulo com furo circular E cantos arredondados (fillet).

    O fillet e essencial no auto-teste: e a unica peca com um ARCO PARCIAL
    (nao um circulo inteiro) na v1 -- exatamente o tipo de geometria que
    revelou o bug de `Arc3D.getData()` (ver face_to_2d.py::_arc_segment_from_arc3d),
    onde os angulos vem medidos a partir do referenceVector proprio da curva,
    nao do eixo +X global.
    """
    sketch = component.sketches.add(component.xYConstructionPlane)
    lines_coll = sketch.sketchCurves.sketchLines
    pts = [(0.0, 0.0), (8.0, 0.0), (8.0, 5.0), (0.0, 5.0)]
    points3d = [adsk.core.Point3D.create(offset_x + x, offset_y + y, 0.0) for x, y in pts]
    n = len(points3d)
    lines = [lines_coll.addByTwoPoints(points3d[i], points3d[(i + 1) % n]) for i in range(n)]

    arcs_coll = sketch.sketchCurves.sketchArcs
    fillet_radius_cm = 0.8
    for i in range(n):
        corner_point = points3d[(i + 1) % n]
        arcs_coll.addFillet(lines[i], corner_point, lines[(i + 1) % n], corner_point, fillet_radius_cm)

    circles = sketch.sketchCurves.sketchCircles
    circles.addByCenterRadius(adsk.core.Point3D.create(offset_x + 4.0, offset_y + 2.5, 0.0), 1.0)

    # O perfil de maior area e o retangulo-com-furo (o furo sozinho e o outro profile).
    profiles = sketch.profiles
    best_index = 0
    best_area = -1.0
    for i in range(profiles.count):
        props = profiles.item(i).areaProperties()
        if props.area > best_area:
            best_area = props.area
            best_index = i
    return _extrude_profile(component, sketch, best_index)


def _tabbed_piece(component: "adsk.fusion.Component", offset_x: float, offset_y: float) -> "adsk.fusion.BRepBody":
    """Retangulo 8x4 cm com dentes de encaixe (zigue-zague) na borda superior."""
    sketch = component.sketches.add(component.xYConstructionPlane)
    lines = sketch.sketchCurves.sketchLines

    pts = [
        (0.0, 0.0),
        (8.0, 0.0),
        (8.0, 3.0),
        (6.5, 3.0),
        (6.5, 4.0),
        (5.0, 4.0),
        (5.0, 3.0),
        (3.0, 3.0),
        (3.0, 4.0),
        (1.5, 4.0),
        (1.5, 3.0),
        (0.0, 3.0),
    ]
    points3d = [adsk.core.Point3D.create(offset_x + x, offset_y + y, 0.0) for x, y in pts]
    for i in range(len(points3d)):
        lines.addByTwoPoints(points3d[i], points3d[(i + 1) % len(points3d)])

    return _extrude_profile(component, sketch)


def _circular_piece(component: "adsk.fusion.Component", offset_x: float, offset_y: float) -> "adsk.fusion.BRepBody":
    sketch = component.sketches.add(component.xYConstructionPlane)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(offset_x, offset_y, 0.0), 3.0)
    return _extrude_profile(component, sketch)


def _piece_on_other_plane(component: "adsk.fusion.Component", offset_x: float, offset_y: float) -> "adsk.fusion.BRepBody":
    sketch = component.sketches.add(component.yZConstructionPlane)
    lines = sketch.sketchCurves.sketchLines
    pts = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]
    points3d = [adsk.core.Point3D.create(offset_x + x, offset_y + y, 0.0) for x, y in pts]
    for i in range(len(points3d)):
        lines.addByTwoPoints(points3d[i], points3d[(i + 1) % len(points3d)])
    return _extrude_profile(component, sketch)


def create_test_document(app: "adsk.core.Application") -> None:
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent

    _rectangle_with_hole(root, 0.0, 0.0)
    _tabbed_piece(root, 12.0, 0.0)
    _circular_piece(root, 27.0, 4.0)
    _piece_on_other_plane(root, 34.0, 0.0)
