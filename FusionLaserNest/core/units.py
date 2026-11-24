"""Conversao de unidades cm <-> mm.

A API do Fusion trabalha sempre internamente em centimetros para comprimento
(Point3D, BRepEdge.length, Matrix3D, etc.), independente da unidade do
documento. A UI deste add-in e sempre em milimetros. 1 cm = 10 mm e uma
constante exata, entao a conversao nao depende de `design.unitsManager`
(que so seria necessario para interpretar *strings* digitadas pelo usuario,
o que e feito pelo proprio ValueCommandInput com unitType='mm').

Modulo puro (sem adsk.*) para poder ser testado com pytest.
"""

CM_PER_MM = 0.1
MM_PER_CM = 10.0


def cm_to_mm(value_cm: float) -> float:
    return value_cm * MM_PER_CM


def mm_to_cm(value_mm: float) -> float:
    return value_mm * CM_PER_MM
