"""Geometria 2D pura (sem nenhum import de adsk.*).

Todas as distancias aqui sao em milimetros (mm). Angulos sao sempre em radianos.
Este modulo e testavel fora do Fusion com pytest puro.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

Point = Tuple[float, float]

EPS = 1e-9


# ---------------------------------------------------------------------------
# Segmentos de curva exata (preservam a geometria original da face)
# ---------------------------------------------------------------------------


@dataclass
class LineSeg:
    p0: Point
    p1: Point


@dataclass
class ArcSeg:
    """Arco sempre orientado CCW (sentido anti-horario), de start_angle para
    end_angle (radianos, medidos a partir do eixo +X), com end_angle > start_angle.
    Esta e a mesma convencao usada pelo SketchArcs.addByCenterStartSweep do Fusion.

    `reversed` NAO muda a forma fisica do arco (center/radius/start_angle/
    end_angle continuam descrevendo o mesmo arco) -- so indica, para quem
    percorre a cadeia de segmentos de um contorno (ver order_segments_into_chain),
    que este segmento deve ser "entrado" por end_point e "saido" por start_point
    em vez do contrario. Necessario porque, ao contrario de LineSeg/SplineSeg,
    nao da para simplesmente trocar os campos que definem a forma do arco.
    """

    center: Point
    radius: float
    start_angle: float
    end_angle: float
    reversed: bool = False

    @property
    def sweep(self) -> float:
        return self.end_angle - self.start_angle

    @property
    def start_point(self) -> Point:
        cx, cy = self.center
        return (cx + self.radius * math.cos(self.start_angle), cy + self.radius * math.sin(self.start_angle))

    @property
    def end_point(self) -> Point:
        cx, cy = self.center
        return (cx + self.radius * math.cos(self.end_angle), cy + self.radius * math.sin(self.end_angle))


@dataclass
class CircleSeg:
    center: Point
    radius: float


@dataclass
class SplineSeg:
    """Aproximacao poligonal de uma NURBS (ou elipse) com tolerancia <= 0.05 mm.

    A curva exata (NurbsCurve3D) e preservada separadamente pelo fusion_adapter
    para reconstrucao no esboco; aqui guardamos apenas os pontos para nesting/SVG.
    """

    points: List[Point]


Segment = Union[LineSeg, ArcSeg, CircleSeg, SplineSeg]


def rotate_point(p: Point, angle: float, origin: Point = (0.0, 0.0)) -> Point:
    ox, oy = origin
    x, y = p[0] - ox, p[1] - oy
    c, s = math.cos(angle), math.sin(angle)
    return (x * c - y * s + ox, x * s + y * c + oy)


def transform_point(p: Point, angle: float, dx: float, dy: float) -> Point:
    x, y = rotate_point(p, angle)
    return (x + dx, y + dy)


def transform_segment(seg: Segment, angle: float, dx: float, dy: float) -> Segment:
    if isinstance(seg, LineSeg):
        return LineSeg(transform_point(seg.p0, angle, dx, dy), transform_point(seg.p1, angle, dx, dy))
    if isinstance(seg, ArcSeg):
        return ArcSeg(
            center=transform_point(seg.center, angle, dx, dy),
            radius=seg.radius,
            start_angle=seg.start_angle + angle,
            end_angle=seg.end_angle + angle,
            reversed=seg.reversed,
        )
    if isinstance(seg, CircleSeg):
        return CircleSeg(center=transform_point(seg.center, angle, dx, dy), radius=seg.radius)
    if isinstance(seg, SplineSeg):
        return SplineSeg(points=[transform_point(p, angle, dx, dy) for p in seg.points])
    raise TypeError(f"Tipo de segmento desconhecido: {type(seg)!r}")


# ---------------------------------------------------------------------------
# Encadeamento de segmentos (necessario porque BRepLoop.edges NAO garante
# ordem conectada head-to-tail -- so BRepLoop.coEdges e documentado como uma
# cadeia ordenada, e mesmo assim precisariamos decifrar isOpposedToEdge para
# cada tipo de curva. Em vez de depender dessa semantica da API, reconstruimos
# a cadeia geometricamente: cada segmento so precisa ter as extremidades
# corretas em espaco 2D (o que ja garantimos), e aqui os encaixamos na ordem e
# direcao corretas comparando distancias entre extremidades.)
# ---------------------------------------------------------------------------


def segment_endpoints(seg: Segment) -> Tuple[Point, Point]:
    """Retorna (ponto_de_entrada, ponto_de_saida) do segmento, na orientacao
    atual (respeitando ArcSeg.reversed)."""
    if isinstance(seg, LineSeg):
        return seg.p0, seg.p1
    if isinstance(seg, ArcSeg):
        return (seg.end_point, seg.start_point) if seg.reversed else (seg.start_point, seg.end_point)
    if isinstance(seg, CircleSeg):
        p = (seg.center[0] + seg.radius, seg.center[1])
        return p, p
    if isinstance(seg, SplineSeg):
        return seg.points[0], seg.points[-1]
    raise TypeError(f"Tipo de segmento desconhecido: {type(seg)!r}")


def reverse_segment(seg: Segment) -> Segment:
    """Retorna um segmento equivalente (mesma forma fisica), mas com entrada e
    saida trocadas."""
    if isinstance(seg, LineSeg):
        return LineSeg(p0=seg.p1, p1=seg.p0)
    if isinstance(seg, ArcSeg):
        return ArcSeg(center=seg.center, radius=seg.radius, start_angle=seg.start_angle, end_angle=seg.end_angle, reversed=not seg.reversed)
    if isinstance(seg, CircleSeg):
        return seg
    if isinstance(seg, SplineSeg):
        return SplineSeg(points=list(reversed(seg.points)))
    raise TypeError(f"Tipo de segmento desconhecido: {type(seg)!r}")


def _point_distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def order_segments_into_chain(segments: Sequence[Segment]) -> List[Segment]:
    """Reordena (e reorienta, via reverse_segment) uma lista de segmentos, ainda
    que venham fora de ordem ou com direcoes misturadas, para formar uma cadeia
    conectada (saida de um = entrada do proximo), escolhendo a cada passo o
    segmento remanescente cuja entrada OU saida fica mais proxima do ponto atual.

    ATENCAO -- isso e so uma REDE DE SEGURANCA (usado quando a fonte dos dados
    nao fornece ordem/direcao confiavel, ou como fallback se a fonte "correta"
    falhar). Nao e o metodo primario para extrair loops do Fusion: quando duas
    arestas diferentes tem pontos muito proximos (comum em pecas com dentes de
    encaixe bem juntos), a escolha "mais proxima" pode ser topologicamente
    errada -- a rota correta e a ordem de `BRepLoop.coEdges` (documentada pela
    Autodesk como cadeia head-to-tail), usada em fusion_adapter/face_to_2d.py."""
    if not segments:
        return []

    remaining = list(segments)
    chain = [remaining.pop(0)]
    current_end = segment_endpoints(chain[0])[1]

    while remaining:
        best_index = 0
        best_reversed = False
        best_dist = math.inf
        for i, seg in enumerate(remaining):
            entry, exit_ = segment_endpoints(seg)
            d_forward = _point_distance(entry, current_end)
            if d_forward < best_dist:
                best_dist, best_index, best_reversed = d_forward, i, False
            d_backward = _point_distance(exit_, current_end)
            if d_backward < best_dist:
                best_dist, best_index, best_reversed = d_backward, i, True

        seg = remaining.pop(best_index)
        if best_reversed:
            seg = reverse_segment(seg)
        chain.append(seg)
        current_end = segment_endpoints(seg)[1]

    return chain


def is_chain_connected(chain: Sequence[Segment], tol: float = 1e-4) -> bool:
    """True se a saida de cada segmento bate com a entrada do proximo (cadeia
    fechada), dentro de `tol` mm. Usado para validar se a ordem/direcao dada
    por uma fonte (ex.: BRepLoop.coEdges) realmente resultou numa cadeia
    conectada antes de confiar nela."""
    if len(chain) < 2:
        return True
    for i in range(len(chain)):
        _entry, exit_ = segment_endpoints(chain[i])
        next_entry, _next_exit = segment_endpoints(chain[(i + 1) % len(chain)])
        if _point_distance(exit_, next_entry) > tol:
            return False
    return True


# ---------------------------------------------------------------------------
# Contornos e pecas
# ---------------------------------------------------------------------------


@dataclass
class Contour:
    """Um loop fechado: geometria exata (segments) + poligono aproximado
    (approx_polygon) usado para calculos geometricos (hull, bbox, nesting, SVG
    fallback)."""

    segments: List[Segment]
    approx_polygon: List[Point]
    is_outer: bool = True

    def transformed(self, angle: float, dx: float, dy: float) -> "Contour":
        return Contour(
            segments=[transform_segment(s, angle, dx, dy) for s in self.segments],
            approx_polygon=[transform_point(p, angle, dx, dy) for p in self.approx_polygon],
            is_outer=self.is_outer,
        )


@dataclass
class PartShape:
    """Peca 2D nivelada, com contorno externo, furos e metadados de nesting."""

    part_id: str
    outer: Contour
    holes: List[Contour] = field(default_factory=list)
    quantity: int = 1
    source_body_name: str = ""

    def transformed(self, angle: float, dx: float, dy: float) -> "PartShape":
        return PartShape(
            part_id=self.part_id,
            outer=self.outer.transformed(angle, dx, dy),
            holes=[h.transformed(angle, dx, dy) for h in self.holes],
            quantity=self.quantity,
            source_body_name=self.source_body_name,
        )


# ---------------------------------------------------------------------------
# Casco convexo (monotone chain) e retangulo minimo (rotating calipers)
# ---------------------------------------------------------------------------


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(points: Sequence[Point]) -> List[Point]:
    """Retorna o casco convexo em ordem CCW, sem ponto repetido no fechamento."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return list(pts)

    lower: List[Point] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= EPS:
            lower.pop()
        lower.append(p)

    upper: List[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= EPS:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def polygon_bbox(points: Sequence[Point]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def polygon_area(points: Sequence[Point]) -> float:
    """Area (sempre positiva) via formula do shoelace."""
    n = len(points)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def point_in_polygon(p: Point, polygon: Sequence[Point]) -> bool:
    """Ray casting. Usado nos testes para verificar furos dentro do contorno."""
    x, y = p
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-300) + x1):
            inside = not inside
    return inside


def min_area_rect_angle(hull: Sequence[Point]) -> float:
    """Rotating calipers: angulo (rad) de UM DOS EIXOS do retangulo de area minima
    que envolve o casco convexo `hull`. Rotacionar o poligono por -angulo alinha
    esse retangulo aos eixos XY.
    """
    n = len(hull)
    if n < 3:
        return 0.0

    best_angle = 0.0
    best_area = math.inf

    for i in range(n):
        p1 = hull[i]
        p2 = hull[(i + 1) % n]
        edge_angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])

        c, s = math.cos(-edge_angle), math.sin(-edge_angle)
        xs = [pt[0] * c - pt[1] * s for pt in hull]
        ys = [pt[0] * s + pt[1] * c for pt in hull]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))

        if area < best_area - EPS:
            best_area = area
            best_angle = edge_angle

    return best_angle


# ---------------------------------------------------------------------------
# Orientacoes candidatas (opcoes de rotacao da UI)
# ---------------------------------------------------------------------------


@dataclass
class Orientation:
    angle_rad: float
    width: float
    height: float
    offset: Point  # subtrai do poligono rotacionado para levar o bbox a (0,0)


def _orientation_from_angle(hull: Sequence[Point], angle: float) -> Orientation:
    rotated = [rotate_point(p, angle) for p in hull]
    minx, miny, maxx, maxy = polygon_bbox(rotated)
    return Orientation(angle_rad=angle, width=maxx - minx, height=maxy - miny, offset=(minx, miny))


def orientation_candidates(hull: Sequence[Point], mode: str) -> List[Orientation]:
    """mode: 'none' | 'rect4' | 'auto'"""
    if not hull:
        return [Orientation(0.0, 0.0, 0.0, (0.0, 0.0))]

    if mode == "none":
        angles = [0.0]
    elif mode == "rect4":
        angles = [0.0, math.pi / 2, math.pi, 3 * math.pi / 2]
    elif mode == "auto":
        base = min_area_rect_angle(hull)
        # Rotacionar por -base alinha o retangulo minimo aos eixos.
        angles = [-base, -base + math.pi / 2]
    else:
        raise ValueError(f"Modo de rotacao desconhecido: {mode!r}")

    return [_orientation_from_angle(hull, a) for a in angles]


# ---------------------------------------------------------------------------
# Posicionamento final (usado depois do nesting para montar esbocos/SVG)
# ---------------------------------------------------------------------------


@dataclass
class PositionedPart:
    part_id: str
    outer: Contour
    holes: List[Contour]
    sheet_index: int


def place_part_shape(shape: PartShape, orientation: Orientation, x: float, y: float, sheet_index: int) -> PositionedPart:
    """Aplica rotacao (orientation.angle_rad) + translacao para que o bbox da peca
    fique com canto inferior-esquerdo em (x, y)."""
    dx = x - orientation.offset[0]
    dy = y - orientation.offset[1]
    transformed = shape.transformed(orientation.angle_rad, dx, dy)
    return PositionedPart(
        part_id=transformed.part_id,
        outer=transformed.outer,
        holes=transformed.holes,
        sheet_index=sheet_index,
    )
