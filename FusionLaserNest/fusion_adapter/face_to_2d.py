"""Nivelamento de uma BRepFace planar no plano XY e extracao da geometria 2D
exata (para reconstrucao em esboco) + poligono aproximado (para nesting).

Esta e a unica parte do add-in que le geometria de B-Rep diretamente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import adsk.core
import adsk.fusion

from ..core.geometry2d import (
    ArcSeg,
    CircleSeg,
    Contour,
    LineSeg,
    PartShape,
    SplineSeg,
    order_segments_into_chain,
)
from ..core.units import cm_to_mm

SPLINE_TOLERANCE_MM = 0.05
SPLINE_TOLERANCE_CM = SPLINE_TOLERANCE_MM * 0.1


def build_leveling_matrix(face: "adsk.fusion.BRepFace") -> "adsk.core.Matrix3D":
    """Monta a matriz que nivela a face no plano XY (normal -> +Z, origem -> 0,0,0),
    usando somente rotacao/translacao (garantido determinante ~= +1).

    Decisao de projeto (ver PLAN.md item 4): construimos a base 'from' nos mesmos
    como um sistema ortonormal a direita a partir de plane.normal e plane.uDirection,
    em vez de confiar que uDirection x vDirection == normal.
    """
    plane = adsk.core.Plane.cast(face.geometry)

    origin = plane.origin
    normal = plane.normal
    normal.normalize()

    u_dir = plane.uDirection
    # Remove qualquer componente de u_dir ao longo da normal (garante ortogonalidade).
    proj = normal.copy()
    proj.scaleBy(u_dir.dotProduct(normal))
    x_axis = u_dir.copy()
    x_axis.subtract(proj)
    if x_axis.length < 1e-9:
        # Caso degenerado extremamente raro: escolhe outro vetor de referencia.
        fallback = adsk.core.Vector3D.create(1.0, 0.0, 0.0)
        if abs(fallback.dotProduct(normal)) > 0.9:
            fallback = adsk.core.Vector3D.create(0.0, 1.0, 0.0)
        proj = normal.copy()
        proj.scaleBy(fallback.dotProduct(normal))
        x_axis = fallback.copy()
        x_axis.subtract(proj)
    x_axis.normalize()

    y_axis = normal.crossProduct(x_axis)
    y_axis.normalize()

    to_origin = adsk.core.Point3D.create(0.0, 0.0, 0.0)
    to_x = adsk.core.Vector3D.create(1.0, 0.0, 0.0)
    to_y = adsk.core.Vector3D.create(0.0, 1.0, 0.0)
    to_z = adsk.core.Vector3D.create(0.0, 0.0, 1.0)

    matrix = adsk.core.Matrix3D.create()
    ok = matrix.setToAlignCoordinateSystems(origin, x_axis, y_axis, normal, to_origin, to_x, to_y, to_z)
    if not ok:
        raise RuntimeError("Falha ao construir a matriz de nivelamento da face.")

    if abs(matrix.determinant - 1.0) > 1e-6:
        raise RuntimeError(
            "A matriz de nivelamento resultou em espelhamento (determinante="
            f"{matrix.determinant:.6f}); abortando para nao inverter a peca."
        )

    return matrix


def _arc_segment_from_arc3d(arc: "adsk.core.Arc3D") -> ArcSeg:
    """Constroi o ArcSeg (mm, angulos medidos a partir do eixo +X global --
    e a convencao que ArcSeg.start_point/end_point assumem, ver geometry2d.py).

    HISTORICO DE BUGS REAIS (dois erros sucessivos ao tentar aproveitar os
    angulos crus de Arc3D.getData(), registrado para nao repetir):

    1) Os angulos devolvidos por `getData()` sao medidos a partir do
       `referenceVector` PROPRIO da curva ("measured from the reference
       vector using the right hand rule around the normal vector"), quase
       nunca alinhado com o eixo +X global. Usar esses angulos diretamente
       como "angulo em relacao a +X" rotaciona o arco todo em torno do
       proprio centro -- primeira tentativa de correcao: usar `arc.startPoint`
       (confiavel) via atan2 para achar o angulo do PONTO INICIAL em relacao
       a +X, mas ainda reaproveitando `sweep = (end_angle - start_angle) %
       2pi` de `getData()` supondo que essa MAGNITUDE (diferenca de dois
       angulos na mesma referencia, nao importa qual) seria confiavel.

    2) Essa suposicao (2) se provou FALSA num caso real (fillet de 90
       graus): a diferenca crua `end_angle - start_angle` veio como 270
       graus (o arco COMPLEMENTAR), nao os 90 graus corretos (confirmados
       comparando com o DXF exportado, que usa uma convencao diferente e
       correta). Ou seja, nem a magnitude do sweep pode ser confiada a
       partir dos angulos crus.

    CORRECAO FINAL: nao usar NENHUM angulo de `getData()`. Em vez disso,
    desambiguar geometricamente com um ponto real do MEIO do arco (via
    `CurveEvaluator3D.getPointAtParameter`, evitando qualquer convencao
    interna do Fusion): dos dois arcos possiveis entre start_point e
    end_point ao redor do mesmo centro (um de `delta_ccw` graus, outro de
    `360 - delta_ccw`), o ponto do meio real so pode estar em UM deles.
    """
    center = arc.center
    radius = arc.radius
    start_point = arc.startPoint
    end_point = arc.endPoint

    start_angle_global = math.atan2(start_point.y - center.y, start_point.x - center.x)
    end_angle_raw = math.atan2(end_point.y - center.y, end_point.x - center.x)
    delta_ccw = (end_angle_raw - start_angle_global) % (2.0 * math.pi)
    if delta_ccw <= 1e-9:
        delta_ccw = 2.0 * math.pi

    evaluator = arc.evaluator
    ok_extents, param_start, param_end = evaluator.getParameterExtents()
    ok_mid, mid_point = evaluator.getPointAtParameter((param_start + param_end) / 2.0)
    mid_angle = math.atan2(mid_point.y - center.y, mid_point.x - center.x)
    mid_offset = (mid_angle - start_angle_global) % (2.0 * math.pi)

    if mid_offset < delta_ccw:
        # O ponto do meio real esta dentro do arco CCW de start ate end: essa
        # e a direcao/magnitude corretas.
        final_start_angle = start_angle_global
        sweep = delta_ccw
    else:
        # O ponto do meio esta do OUTRO lado: o arco fisico correto e o
        # complementar, percorrido de end_point ate start_point.
        final_start_angle = end_angle_raw
        sweep = (2.0 * math.pi) - delta_ccw

    return ArcSeg(
        center=(cm_to_mm(center.x), cm_to_mm(center.y)),
        radius=cm_to_mm(radius),
        start_angle=final_start_angle,
        end_angle=final_start_angle + sweep,
    )


def _polyline_points(curve: "adsk.core.Curve3D") -> List[Tuple[float, float]]:
    evaluator = curve.evaluator
    ok, start_param, end_param = evaluator.getParameterExtents()
    ok2, _points = evaluator.getStrokes(start_param, end_param, SPLINE_TOLERANCE_CM)
    return [(cm_to_mm(p.x), cm_to_mm(p.y)) for p in _points]


def _segment_from_curve(curve: "adsk.core.Curve3D") -> object:
    # Comparacao por objectType/classType, conforme o padrao usado em toda a
    # documentacao oficial (ex.: "if obj.objectType == adsk.core.Point3D.classType()").
    obj_type = curve.objectType
    if obj_type == adsk.core.Line3D.classType():
        line = adsk.core.Line3D.cast(curve)
        return LineSeg(
            p0=(cm_to_mm(line.startPoint.x), cm_to_mm(line.startPoint.y)),
            p1=(cm_to_mm(line.endPoint.x), cm_to_mm(line.endPoint.y)),
        )
    if obj_type == adsk.core.Arc3D.classType():
        return _arc_segment_from_arc3d(adsk.core.Arc3D.cast(curve))
    if obj_type == adsk.core.Circle3D.classType():
        circle = adsk.core.Circle3D.cast(curve)
        return CircleSeg(center=(cm_to_mm(circle.center.x), cm_to_mm(circle.center.y)), radius=cm_to_mm(circle.radius))

    # Ellipse3D, EllipticalArc3D, NurbsCurve3D e qualquer outro tipo: aproxima por
    # polilinha (tolerancia <= 0.05 mm), preservando exatidao suficiente para corte
    # a laser. A curva exata (NurbsCurve3D) e reconstruida no esboco a partir do
    # proprio `curve` transformado (ver sketch_builder.py), nao a partir do SplineSeg.
    return SplineSeg(points=_polyline_points(curve))


@dataclass
class LoopData:
    is_outer: bool
    exact_curves: List["adsk.core.Curve3D"]  # ja transformadas (copy + transformBy)
    contour: Contour


def _polygon_points_for_segment(seg) -> List[Tuple[float, float]]:
    if isinstance(seg, CircleSeg):
        n = 64
        return [
            (
                seg.center[0] + seg.radius * math.cos(2 * math.pi * i / n),
                seg.center[1] + seg.radius * math.sin(2 * math.pi * i / n),
            )
            for i in range(n)
        ]
    if isinstance(seg, ArcSeg):
        n = max(8, int(abs(seg.sweep) / (math.pi / 24)))
        points = [
            (
                seg.center[0] + seg.radius * math.cos(seg.start_angle + seg.sweep * i / n),
                seg.center[1] + seg.radius * math.sin(seg.start_angle + seg.sweep * i / n),
            )
            for i in range(n + 1)
        ]
        return list(reversed(points)) if seg.reversed else points
    if isinstance(seg, LineSeg):
        return [seg.p0, seg.p1]
    if isinstance(seg, SplineSeg):
        return list(seg.points)
    raise TypeError(f"Tipo de segmento desconhecido: {type(seg)!r}")


def _extract_loop(loop: "adsk.fusion.BRepLoop", matrix: "adsk.core.Matrix3D") -> LoopData:
    """Extrai TODAS as arestas do loop e (so por qualidade, nao por
    necessidade) tenta encadea-las numa ordem bonita para o poligono aproximado.

    HISTORICO (duas tentativas anteriores que pareciam certas na doc mas nao
    resolveram de verdade -- registrado para nao repetir o erro):
    1) `loop.edges` "pareceu" nao ordenado -> trocamos para percorrer
       `loop.coEdges` (documentado como "ordered head-to-tail") via
       `BRepCoEdge.next`, usando `isOpposedToEdge` para decidir a direcao.
    2) Isso continuou produzindo contornos com arestas FALTANDO (nao so fora
       de ordem) -- ou seja, o problema nunca foi ordem/direcao, e sim que a
       travessia via `.next` nao estava visitando todas as arestas do loop
       (por motivo que a documentacao nao deixa claro; pode repetir alguma
       co-edge e pular outra).

    A causa raiz do bug original (ziguezague) ja foi corrigida de outra forma:
    `core/svg_writer.py` desenha cada segmento como um sub-path SVG
    independente (`M` proprio por segmento), entao a ORDEM da lista de
    segmentos deixou de importar para a forma exportada estar certa -- so
    precisamos ter a certeza de que NENHUMA aresta falta. `loop.edges` e
    documentado simplesmente como "Returns the BRepEdges used by this loop":
    um conjunto completo, mesmo que nao prometa ordem. Por isso voltamos a
    ele como fonte, e usamos `order_segments_into_chain` so como acabamento
    (nunca descarta nada -- e uma permutacao/inversao do que ja foi
    extraido) para o poligono aproximado (usado em nesting) ficar com pontos
    em sequencia ao redor do contorno."""
    exact_curves: List[adsk.core.Curve3D] = []
    raw_segments = []

    for edge_index in range(loop.edges.count):
        edge = loop.edges.item(edge_index)
        curve = edge.geometry.copy()
        curve.transformBy(matrix)
        exact_curves.append(curve)
        raw_segments.append(_segment_from_curve(curve))

    segments = order_segments_into_chain(raw_segments)

    polygon: List[Tuple[float, float]] = []
    for seg in segments:
        polygon.extend(_polygon_points_for_segment(seg))

    contour = Contour(segments=segments, approx_polygon=polygon, is_outer=loop.isOuter)
    return LoopData(is_outer=loop.isOuter, exact_curves=exact_curves, contour=contour)


@dataclass
class FacePartData:
    part_shape: PartShape
    exact_outer_curves: List["adsk.core.Curve3D"]
    exact_hole_curves: List[List["adsk.core.Curve3D"]]


def extract_part_from_face(face: "adsk.fusion.BRepFace", part_id: str, quantity: int) -> FacePartData:
    matrix = build_leveling_matrix(face)

    outer_loop_data = None
    hole_loops_data: List[LoopData] = []

    for loop_index in range(face.loops.count):
        loop = face.loops.item(loop_index)
        data = _extract_loop(loop, matrix)
        if data.is_outer:
            outer_loop_data = data
        else:
            hole_loops_data.append(data)

    if outer_loop_data is None:
        raise RuntimeError(f"A face '{face.body.name}' nao possui um loop externo valido.")

    part_shape = PartShape(
        part_id=part_id,
        outer=outer_loop_data.contour,
        holes=[h.contour for h in hole_loops_data],
        quantity=quantity,
        source_body_name=face.body.name,
    )

    return FacePartData(
        part_shape=part_shape,
        exact_outer_curves=outer_loop_data.exact_curves,
        exact_hole_curves=[h.exact_curves for h in hole_loops_data],
    )
