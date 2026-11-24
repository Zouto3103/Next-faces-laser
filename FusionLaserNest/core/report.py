"""Monta o texto do relatorio final (pt-BR), exibido em ui.messageBox.

Python puro, sem adsk.*.
"""
from __future__ import annotations

from typing import List

from .nesting import PackResult


def build_report_text(result: PackResult, total_parts: int) -> str:
    lines: List[str] = []
    placed_count = len(result.placements)
    lines.append("Relatorio de nesting")
    lines.append("=====================")
    lines.append(f"Pecas alocadas: {placed_count} de {total_parts}")

    if result.unplaced:
        lines.append("")
        lines.append(
            f"ATENCAO: {len(result.unplaced)} peca(s) NAO couberam na chapa e NAO foram "
            "desenhadas nem exportadas. Aumente a chapa, reduza a quantidade ou use mais "
            "chapas manualmente para essas:"
        )
        for pid in result.unplaced:
            lines.append(f"  - {pid}")
    else:
        lines.append("Nenhuma peca ficou de fora.")

    lines.append(f"Numero de chapas usadas: {result.sheet_count}")
    for sheet in result.sheets:
        pct = sheet.utilization * 100.0
        lines.append(f"  Chapa {sheet.index + 1}: aproveitamento {pct:.1f}%")

    return "\n".join(lines)
