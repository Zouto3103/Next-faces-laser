"""Algoritmo de nesting (encaixe) em retangulos envolventes.

Python puro (sem adsk.*), plugavel: qualquer classe que implemente o protocolo
`Nester` (metodo `pack`) pode substituir `MaxRectsNester` no futuro (por exemplo
por um nesting poligonal), sem tocar no resto do add-in.

Algoritmo: MaxRects com heuristica Best-Area-Fit (Jylanki, "A Thousand Ways to
Pack the Bin"), com espacamento entre pecas reservado como uma margem extra no
lado direito/superior de cada retangulo ao inserir na lista de livres, e margem
da chapa aplicada encolhendo a area util antes do nesting.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Tuple

from .geometry2d import Orientation


@dataclass
class PartForNesting:
    part_id: str
    orientations: List[Orientation]
    area: float  # area real da peca (poligono), usada so para ordenar/relatorio


@dataclass
class Placement:
    part_id: str
    sheet_index: int
    x: float  # posicao (mm) do canto inferior-esquerdo do bbox, relativa a AREA UTIL da chapa (apos margem)
    y: float
    orientation: Orientation


@dataclass
class SheetResult:
    index: int
    usable_width: float
    usable_height: float
    used_area: float = 0.0

    @property
    def utilization(self) -> float:
        total = self.usable_width * self.usable_height
        if total <= 0:
            return 0.0
        return self.used_area / total


@dataclass
class PackResult:
    placements: List[Placement] = field(default_factory=list)
    unplaced: List[str] = field(default_factory=list)
    sheets: List[SheetResult] = field(default_factory=list)

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)


class Nester(Protocol):
    def pack(
        self,
        parts: List[PartForNesting],
        sheet_width: float,
        sheet_height: float,
        spacing: float,
        margin: float,
        max_sheets: int = 200,
    ) -> PackResult:
        ...


@dataclass
class _FreeRect:
    x: float
    y: float
    w: float
    h: float

    @property
    def area(self) -> float:
        return self.w * self.h


def _rects_intersect(a: _FreeRect, x: float, y: float, w: float, h: float) -> bool:
    return not (x >= a.x + a.w - 1e-9 or x + w <= a.x + 1e-9 or y >= a.y + a.h - 1e-9 or y + h <= a.y + 1e-9)


def _contained(a: _FreeRect, b: _FreeRect) -> bool:
    """True se `a` esta totalmente contido em `b`."""
    return (
        a.x >= b.x - 1e-9
        and a.y >= b.y - 1e-9
        and a.x + a.w <= b.x + b.w + 1e-9
        and a.y + a.h <= b.y + b.h + 1e-9
    )


class _MaxRectsSheet:
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height
        self.free_rects: List[_FreeRect] = [_FreeRect(0.0, 0.0, width, height)]

    def _split_around(self, f: _FreeRect, x: float, y: float, w: float, h: float) -> List[_FreeRect]:
        pieces: List[_FreeRect] = []
        # esquerda
        if x > f.x + 1e-9:
            pieces.append(_FreeRect(f.x, f.y, x - f.x, f.h))
        # direita
        if x + w < f.x + f.w - 1e-9:
            pieces.append(_FreeRect(x + w, f.y, (f.x + f.w) - (x + w), f.h))
        # baixo
        if y > f.y + 1e-9:
            pieces.append(_FreeRect(f.x, f.y, f.w, y - f.y))
        # cima
        if y + h < f.y + f.h - 1e-9:
            pieces.append(_FreeRect(f.x, y + h, f.w, (f.y + f.h) - (y + h)))
        return [p for p in pieces if p.w > 1e-9 and p.h > 1e-9]

    def _prune(self) -> None:
        kept: List[_FreeRect] = []
        for i, a in enumerate(self.free_rects):
            dominated = False
            for j, b in enumerate(self.free_rects):
                if i != j and _contained(a, b):
                    if _contained(b, a) and i > j:
                        continue
                    dominated = True
                    break
            if not dominated:
                kept.append(a)
        self.free_rects = kept

    def best_fit(self, w: float, h: float) -> Optional[Tuple[float, float]]:
        best: Optional[_FreeRect] = None
        best_leftover = math.inf
        for f in self.free_rects:
            if w <= f.w + 1e-9 and h <= f.h + 1e-9:
                leftover = f.area - w * h
                if leftover < best_leftover - 1e-9:
                    best_leftover = leftover
                    best = f
        if best is None:
            return None
        return (best.x, best.y)

    def place(self, x: float, y: float, w: float, h: float) -> None:
        new_free: List[_FreeRect] = []
        for f in self.free_rects:
            if not _rects_intersect(f, x, y, w, h):
                new_free.append(f)
            else:
                new_free.extend(self._split_around(f, x, y, w, h))
        self.free_rects = new_free
        self._prune()


def _first_orientation_metric(part: PartForNesting, key: str) -> float:
    o0 = part.orientations[0]
    if key == "area":
        return part.area
    if key == "max_dim":
        return max(o0.width, o0.height)
    if key == "min_dim":
        return min(o0.width, o0.height)
    if key == "perimeter":
        return 2.0 * (o0.width + o0.height)
    if key == "width":
        return o0.width
    if key == "height":
        return o0.height
    raise ValueError(f"Estrategia de ordenacao desconhecida: {key!r}")


# Estrategias de ordenacao tentadas por MaxRectsNester.pack -- ver docstring.
_SORT_STRATEGIES = ("area", "max_dim", "perimeter", "width", "height", "min_dim")


class MaxRectsNester:
    """MaxRects / Best-Area-Fit (Jylanki), com suporte a multiplas chapas e a
    varias orientacoes candidatas por peca (rotacao).

    Nao e uma busca exaustiva/otima (isso seria um problema NP-difícil), mas
    tambem nao se contenta com um unico passe guloso: `pack()` roda o mesmo
    algoritmo de encaixe varias vezes, cada vez ordenando as pecas por um
    criterio diferente antes de comecar (area, maior lado, perimetro, largura,
    altura, menor lado -- todos decrescentes), e fica com o resultado que
    aloca mais pecas, depois usa menos chapas, depois tem o maior
    aproveitamento medio. Ordens diferentes levam MaxRects a decisoes
    bem diferentes (a primeira peca "trava" o layout inicial das chapas),
    entao tentar varias e uma forma pratica e barata de melhorar o resultado
    sem implementar um metaheuristico completo (recozimento simulado,
    algoritmo genetico etc.) -- ver README, secao Decisoes."""

    def pack(
        self,
        parts: List[PartForNesting],
        sheet_width: float,
        sheet_height: float,
        spacing: float,
        margin: float,
        max_sheets: int = 200,
    ) -> PackResult:
        if not parts:
            return PackResult()

        usable_w = max(sheet_width - 2 * margin, 0.0)
        usable_h = max(sheet_height - 2 * margin, 0.0)

        if usable_w <= 0 or usable_h <= 0:
            result = PackResult()
            result.unplaced = [p.part_id for p in parts]
            return result

        best_result: Optional[PackResult] = None
        best_score = None

        for strategy in _SORT_STRATEGIES:
            ordered = sorted(parts, key=lambda p: _first_orientation_metric(p, strategy), reverse=True)
            candidate = self._pack_ordered(ordered, usable_w, usable_h, spacing, margin, max_sheets)
            score = self._score(candidate)
            if best_score is None or score < best_score:
                best_score = score
                best_result = candidate

        return best_result

    @staticmethod
    def _score(result: PackResult) -> Tuple[int, int, float]:
        avg_utilization = (
            sum(s.utilization for s in result.sheets) / len(result.sheets) if result.sheets else 0.0
        )
        # Minimizar: menos pecas nao-alocadas, depois menos chapas, depois
        # maior aproveitamento medio (por isso o sinal negativo).
        return (len(result.unplaced), result.sheet_count, -avg_utilization)

    @staticmethod
    def _pack_ordered(
        ordered: List[PartForNesting],
        usable_w: float,
        usable_h: float,
        spacing: float,
        margin: float,
        max_sheets: int,
    ) -> PackResult:
        result = PackResult()
        sheets: List[_MaxRectsSheet] = []
        sheet_results: List[SheetResult] = []

        def ensure_sheet(index: int) -> _MaxRectsSheet:
            while len(sheets) <= index:
                sheets.append(_MaxRectsSheet(usable_w, usable_h))
                sheet_results.append(SheetResult(index=len(sheet_results), usable_width=usable_w, usable_height=usable_h))
            return sheets[index]

        for part in ordered:
            placed = False

            # dimensoes "inflacionadas" pelo espacamento (reserva folga a direita/acima)
            candidates = [(o, o.width + spacing, o.height + spacing) for o in part.orientations]

            sheet_index = 0
            while not placed:
                if sheet_index >= max_sheets:
                    break

                is_new_sheet = sheet_index == len(sheets)
                sheet = ensure_sheet(sheet_index)

                best_choice = None  # (leftover, orientation, x, y, w, h)
                for orientation, w, h in candidates:
                    if w > usable_w + 1e-9 or h > usable_h + 1e-9:
                        continue
                    pos = sheet.best_fit(w, h)
                    if pos is None:
                        continue
                    leftover = w * h  # comparado entre orientacoes: menor area ocupada primeiro
                    if best_choice is None or leftover < best_choice[0]:
                        best_choice = (leftover, orientation, pos[0], pos[1], w, h)

                if best_choice is not None:
                    _, orientation, x, y, w, h = best_choice
                    sheet.place(x, y, w, h)
                    result.placements.append(Placement(part_id=part.part_id, sheet_index=sheet_index, x=x, y=y, orientation=orientation))
                    sheet_results[sheet_index].used_area += orientation.width * orientation.height
                    placed = True
                    break

                if is_new_sheet:
                    # Nao coube nem numa chapa totalmente vazia: peca grande demais.
                    break

                sheet_index += 1

            if not placed:
                result.unplaced.append(part.part_id)

        result.sheets = sheet_results
        return result
