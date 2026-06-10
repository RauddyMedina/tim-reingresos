"""
tim_common.py
=============
Helpers compartidos por los builders Easy/Paris:
  - parseo tolerante de IDs (línea / coma / espacio / punto y coma)
  - resolución de la ruta de plantillas
  - localización dinámica de la fila de header
  - copia de estilo de una fila a otra (para extender la tabla si faltan filas)
"""

from __future__ import annotations

import re
from copy import copy
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def parse_ids(raw: str) -> list[str]:
    """Separa por salto de línea, coma, punto y coma o espacios. Únicos, en orden."""
    if not raw:
        return []
    tokens = re.split(r"[\s,;]+", raw.strip())
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        t = t.strip()
        if t.endswith(".0") and t[:-2].isdigit():
            t = t[:-2]
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def find_header_row(ws, marker: str, max_row: int = 20) -> int:
    """Devuelve el nº de fila (1-based) donde alguna celda == marker (case-insensitive)."""
    target = marker.strip().lower()
    for r in range(1, max_row + 1):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if v is not None and str(v).strip().lower() == target:
                return r
    raise ValueError(f"No se encontró la fila de header con '{marker}' en la plantilla.")


def copy_row_style(ws, src_row: int, dst_row: int, col_start: int, col_end: int) -> None:
    """Copia estilo (no valor) celda a celda de src_row a dst_row en [col_start, col_end]."""
    for c in range(col_start, col_end + 1):
        s = ws.cell(src_row, c)
        d = ws.cell(dst_row, c)
        if s.has_style:
            d.font = copy(s.font)
            d.border = copy(s.border)
            d.fill = copy(s.fill)
            d.number_format = copy(s.number_format)
            d.protection = copy(s.protection)
            d.alignment = copy(s.alignment)
    ws.row_dimensions[dst_row].height = ws.row_dimensions[src_row].height
