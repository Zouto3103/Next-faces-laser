"""Validacao da selecao de faces feita pelo usuario.

Unica responsabilidade: olhar as BRepFace selecionadas e decidir quais sao
validas, alem de detectar o caso de duas faces do mesmo corpo (provavel
duplicata face superior/inferior), que deve ser um AVISO, nao um bloqueio.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import adsk.core
import adsk.fusion


@dataclass
class SelectionCheckResult:
    valid_faces: List["adsk.fusion.BRepFace"]
    rejected_non_planar: int
    duplicate_body_warning: List[str]


def collect_selected_faces(selection_input: "adsk.core.SelectionCommandInput") -> SelectionCheckResult:
    faces: List[adsk.fusion.BRepFace] = []
    rejected = 0

    for i in range(selection_input.selectionCount):
        entity = selection_input.selection(i).entity
        face = adsk.fusion.BRepFace.cast(entity)
        if face is None:
            rejected += 1
            continue
        if face.geometry.objectType != adsk.core.Plane.classType():
            rejected += 1
            continue
        faces.append(face)

    seen_bodies = {}
    duplicate_body_names: List[str] = []
    for face in faces:
        body_id = id(face.body)
        seen_bodies.setdefault(body_id, []).append(face)

    for body_id, body_faces in seen_bodies.items():
        if len(body_faces) > 1:
            duplicate_body_names.append(body_faces[0].body.name)

    return SelectionCheckResult(
        valid_faces=faces,
        rejected_non_planar=rejected,
        duplicate_body_warning=duplicate_body_names,
    )
