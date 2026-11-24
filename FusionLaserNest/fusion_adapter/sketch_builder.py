"""Cria o componente NEST_<timestamp>, os esbocos (um por chapa) e reconstroi as
curvas exatas (linha/arco/circulo/NURBS) na posicao final decidida pelo nesting.

So esta camada cria geometria no documento (alem de exporter.py, que so le
esbocos ja criados). O design original nunca e tocado: tudo e criado dentro de
um componente novo -- EXCETO no caso descrito em NestContainer abaixo.
"""
from __future__ import annotations

import math
from typing import List, Optional

import adsk.core
import adsk.fusion

from ..core.geometry2d import Orientation
from ..core.units import mm_to_cm

NEST_PREFIX = "NEST_"


def delete_previous_nest_artifacts(design: "adsk.fusion.Design") -> int:
    """Apaga occurrences/esbocos de execucoes anteriores do add-in (nome comeca
    com NEST_), tanto o caso normal (Occurrence na raiz) quanto o fallback de
    documentos tipo Peca (esbocos soltos direto na raiz -- ver NestContainer).
    Usado quando o usuario marca 'Substituir esbocos de execucoes anteriores',
    para nao precisar apagar manualmente antes de rodar de novo depois de
    editar a peca. Retorna quantos itens foram apagados."""
    root = design.rootComponent
    deleted = 0

    for i in range(root.occurrences.count - 1, -1, -1):
        occ = root.occurrences.item(i)
        if occ.component.name.startswith(NEST_PREFIX):
            occ.deleteMe()
            deleted += 1

    for i in range(root.sketches.count - 1, -1, -1):
        sketch = root.sketches.item(i)
        if sketch.name.startswith(NEST_PREFIX):
            sketch.deleteMe()
            deleted += 1

    return deleted


class NestContainer:
    """Guarda onde os esbocos de nesting foram criados, para permitir limpeza
    (rollback em erro, ou remocao quando 'Criar esbocos no design' esta
    desmarcado) sem depender de comparar referencias de objeto do Fusion
    (nao confiavel -- ver create_nest_component).

    Caso normal (documentos tipo Montagem): `occurrence` e a Occurrence do
    componente NEST_* novo; cleanup() so precisa apagar essa Occurrence.

    Caso de fallback (documentos tipo Peca -- ver create_nest_component): nao
    ha `occurrence`; os esbocos foram criados direto no componente raiz e
    precisam ser apagados individualmente.
    """

    def __init__(self, component: "adsk.fusion.Component", occurrence: Optional["adsk.fusion.Occurrence"]):
        self.component = component
        self.occurrence = occurrence
        self.is_fallback = occurrence is None
        self._sketches: List["adsk.fusion.Sketch"] = []

    def register_sketch(self, sketch: "adsk.fusion.Sketch") -> None:
        self._sketches.append(sketch)

    def cleanup(self) -> None:
        if self.occurrence is not None:
            self.occurrence.deleteMe()
            return
        for sketch in self._sketches:
            try:
                sketch.deleteMe()
            except Exception:
                pass
        self._sketches.clear()


def create_nest_component(design: "adsk.fusion.Design", name: str) -> NestContainer:
    """Cria um componente novo (Occurrence) na raiz para os esbocos de nesting.

    ATENCAO: documentos do tipo "Peca" (Part Design) no Fusion aceitam apenas
    UM componente (Occurrences.addNewComponent falha com RuntimeError: "Os
    documentos de projeto de peca so podem conter um componente."). Como criar
    um documento NOVO nao e suportado dentro do evento execute de um comando
    (ver Documents.add: "Creating a document is not supported within any of
    the Command related events"), a unica saida nesse caso e usar o proprio
    componente raiz do documento atual -- os esbocos criados la sao entao
    apagados individualmente se o usuario desmarcar "Criar esbocos no design"
    ou se ocorrer um erro (ver NestContainer.cleanup)."""
    root = design.rootComponent
    identity = adsk.core.Matrix3D.create()
    try:
        occurrence = root.occurrences.addNewComponent(identity)
        occurrence.component.name = name
        return NestContainer(component=occurrence.component, occurrence=occurrence)
    except RuntimeError:
        return NestContainer(component=root, occurrence=None)


def create_sheet_sketch(component: "adsk.fusion.Component", sheet_label: str) -> "adsk.fusion.Sketch":
    sketch = component.sketches.add(component.xYConstructionPlane)
    sketch.name = sheet_label
    return sketch


def draw_sheet_outline(sketch: "adsk.fusion.Sketch", width_mm: float, height_mm: float) -> None:
    """Desenha o contorno da chapa como geometria de CONSTRUCAO (nao exportada)."""
    w = mm_to_cm(width_mm)
    h = mm_to_cm(height_mm)
    lines = sketch.sketchCurves.sketchLines
    p0 = adsk.core.Point3D.create(0.0, 0.0, 0.0)
    p1 = adsk.core.Point3D.create(w, 0.0, 0.0)
    p2 = adsk.core.Point3D.create(w, h, 0.0)
    p3 = adsk.core.Point3D.create(0.0, h, 0.0)
    rect = [
        lines.addByTwoPoints(p0, p1),
        lines.addByTwoPoints(p1, p2),
        lines.addByTwoPoints(p2, p3),
        lines.addByTwoPoints(p3, p0),
    ]
    for line in rect:
        line.isConstruction = True


def _placement_transform(angle_rad: float, dx_cm: float, dy_cm: float) -> List["adsk.core.Matrix3D"]:
    """Retorna, em ordem de aplicacao, as matrizes de rotacao (em torno da origem,
    eixo Z) e translacao a aplicar via transformBy sucessivos (a ordem das duas
    chamadas ja garante rotacionar-depois-transladar, sem depender de como o
    Fusion compoe matrizes internamente)."""
    matrices = []
    if abs(angle_rad) > 1e-12:
        rot = adsk.core.Matrix3D.create()
        rot.setToRotation(angle_rad, adsk.core.Vector3D.create(0.0, 0.0, 1.0), adsk.core.Point3D.create(0.0, 0.0, 0.0))
        matrices.append(rot)
    if abs(dx_cm) > 1e-12 or abs(dy_cm) > 1e-12:
        trans = adsk.core.Matrix3D.create()
        trans.translation = adsk.core.Vector3D.create(dx_cm, dy_cm, 0.0)
        matrices.append(trans)
    return matrices


def _transform_curve(curve: "adsk.core.Curve3D", matrices: List["adsk.core.Matrix3D"]) -> "adsk.core.Curve3D":
    result = curve.copy()
    for m in matrices:
        result.transformBy(m)
    return result


def _draw_arc(sketch: "adsk.fusion.Sketch", arc: "adsk.core.Arc3D") -> None:
    sweep_magnitude = arc.endAngle - arc.startAngle
    center = arc.center
    start_point = arc.startPoint
    end_point = arc.endPoint

    ang_start = math.atan2(start_point.y - center.y, start_point.x - center.x)
    ang_end = math.atan2(end_point.y - center.y, end_point.x - center.x)
    delta_ccw = (ang_end - ang_start) % (2.0 * math.pi)
    if delta_ccw <= 1e-9:
        delta_ccw = 2.0 * math.pi

    # A geometria original (arc.startAngle/endAngle) e definida em torno da
    # normal PROPRIA da curva, que pode ter sido invertida pelo nivelamento.
    # `delta_ccw` e calculado so a partir das posicoes (start/end/center), entao
    # e sempre correto geometricamente; escolhemos o sinal do sweep comparando
    # com a magnitude original para reproduzir o MESMO arco (nao o complementar).
    if abs(delta_ccw - sweep_magnitude) <= abs((2.0 * math.pi - delta_ccw) - sweep_magnitude):
        sweep = delta_ccw
    else:
        sweep = -sweep_magnitude

    sketch.sketchCurves.sketchArcs.addByCenterStartSweep(center, start_point, sweep)


def _draw_curve(sketch: "adsk.fusion.Sketch", curve: "adsk.core.Curve3D") -> None:
    obj_type = curve.objectType
    if obj_type == adsk.core.Line3D.classType():
        line = adsk.core.Line3D.cast(curve)
        sketch.sketchCurves.sketchLines.addByTwoPoints(line.startPoint, line.endPoint)
    elif obj_type == adsk.core.Arc3D.classType():
        _draw_arc(sketch, adsk.core.Arc3D.cast(curve))
    elif obj_type == adsk.core.Circle3D.classType():
        circle = adsk.core.Circle3D.cast(curve)
        sketch.sketchCurves.sketchCircles.addByCenterRadius(circle.center, circle.radius)
    else:
        # Ellipse3D, EllipticalArc3D, NurbsCurve3D (ou qualquer outra curva
        # exotica): convertida para NURBS exata e inserida como spline fixa
        # (preserva a forma exata; SketchFixedSplines.addByNurbsCurve substitui
        # o metodo retirado SketchFittedSplines.addByNurbsCurve).
        if obj_type == adsk.core.NurbsCurve3D.classType():
            nurbs = adsk.core.NurbsCurve3D.cast(curve)
        else:
            nurbs = curve.asNurbsCurve()
        sketch.sketchCurves.sketchFixedSplines.addByNurbsCurve(nurbs)


def place_and_draw_part(
    sketch: "adsk.fusion.Sketch",
    exact_outer_curves: List["adsk.core.Curve3D"],
    exact_hole_curves: List[List["adsk.core.Curve3D"]],
    orientation: Orientation,
    x_mm: float,
    y_mm: float,
) -> None:
    """Aplica a transformacao decidida pelo nesting (rotacao + translacao, em mm
    convertido para cm) e recria a geometria exata (contorno + furos) no esboco.

    IMPORTANTE: `orientation.offset` precisa ser subtraido de (x_mm, y_mm) antes
    de traduzir -- e o canto minimo do bounding-box do contorno JA ROTACIONADO
    (mas ainda nao transladado), que normalmente NAO e (0,0) porque a origem
    local da face nivelada raramente cai exatamente no canto do seu proprio
    bounding-box. Sem isso, cada peca fica deslocada por esse offset (diferente
    por peca/orientacao) em vez de cair exatamente na posicao decidida pelo
    nesting -- e o mesmo calculo que core/geometry2d.py::place_part_shape() ja
    faz para o SVG."""
    dx_mm = x_mm - orientation.offset[0]
    dy_mm = y_mm - orientation.offset[1]
    matrices = _placement_transform(orientation.angle_rad, mm_to_cm(dx_mm), mm_to_cm(dy_mm))

    for curve in exact_outer_curves:
        transformed = _transform_curve(curve, matrices)
        _draw_curve(sketch, transformed)

    for hole_curves in exact_hole_curves:
        for curve in hole_curves:
            transformed = _transform_curve(curve, matrices)
            _draw_curve(sketch, transformed)
