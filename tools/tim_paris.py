"""
tim_paris.py
============
Genera el formato "Devoluciones RDD" de Paris a partir de números de guía
(=Orden). Fuente: BASE DATOS PARIS (E=Orden, AZ=SKU, BA=desc, BE='RETORNO').

Por cada Orden: una fila por línea de producto, dedup por nombre prefiriendo el
SKU real (descarta cartonid largos tipo '1-6CB627FA3C...').
Tipo Guia = "Retiro" si la línea es RETORNO, si no "Entrega".
Solo se rellenan columnas derivables; el resto queda en blanco para llenado manual.

API:
    build_paris(ids, fecha) -> dict con 'xlsx_bytes', 'preview', 'no_encontrados'
"""

from __future__ import annotations

import datetime as dt
import re
from io import BytesIO

import openpyxl

from tools.db_sources import read_paris
from tools.tim_common import TEMPLATES_DIR, copy_row_style, find_header_row

TEMPLATE = TEMPLATES_DIR / "devoluciones_paris_template.xlsx"

# Columnas del formato (1-based) — fila de datos
COL_N = 2        # B  N°
COL_TIPO = 3     # C  Tipo Guia
COL_GUIA = 4     # D  N° Guia (orden)
COL_SKU = 6      # F  Sku
COL_DESC = 7     # G  Desc. Sku
COL_RANGE = (2, 11)  # B..K

# Un cartonid se ve como '1-6CB627FA3C6044D4B64242359B0A847A' (prefijo dígito-guion + hex largo)
_CARTONID_RE = re.compile(r"^\d-[0-9A-Fa-f]{16,}$")


def _is_real_sku(sku: str) -> bool:
    return bool(sku) and not _CARTONID_RE.match(sku.strip())


def _collect(ids: list[str]):
    """Devuelve (filas, no_encontrados). filas: [{'orden','tipo','sku','desc'}]."""
    paris = read_paris()
    filas: list[dict] = []
    no_encontrados: list[str] = []

    for orden in ids:
        lineas = paris.get(orden)
        if not lineas:
            no_encontrados.append(orden)
            continue
        # dedup por nombre de producto, prefiriendo SKU real
        por_nombre: dict[str, dict] = {}
        orden_nombres: list[str] = []
        for ln in lineas:
            nombre = ln["desc"]
            key = nombre.lower()
            cand = {
                "orden": orden,
                "tipo": "Retiro" if ln["retorno"] else "Entrega",
                "sku": ln["sku"],
                "desc": nombre,
            }
            if key not in por_nombre:
                por_nombre[key] = cand
                orden_nombres.append(key)
            else:
                # si el existente no tiene SKU real y el nuevo sí, reemplazar
                if not _is_real_sku(por_nombre[key]["sku"]) and _is_real_sku(ln["sku"]):
                    por_nombre[key] = cand
        for key in orden_nombres:
            filas.append(por_nombre[key])
    return filas, no_encontrados


def build_paris(ids: list[str], fecha: dt.date | None = None) -> dict:
    fecha = fecha or dt.date.today()
    filas, no_encontrados = _collect(ids)

    wb = openpyxl.load_workbook(TEMPLATE)
    ws = wb.active

    # Defensa: normalizar la vista del libro (evita el aviso de reparación de Excel
    # si la plantilla quedara con un firstSheet fuera de rango).
    for view in getattr(wb, "views", []) or []:
        view.firstSheet = 0
        view.activeTab = 0

    header_row = find_header_row(ws, "N° Guia")  # fila 11
    data_start = header_row + 1
    last_template_row = data_start + 29  # plantilla trae 30 filas pre-formateadas (12..41)

    # Cabecera: Fecha (G8 está combinado H8:I8 con la etiqueta; el valor va al lado).
    # "Total Guias" = nº de guías (órdenes) distintas encontradas.
    guias_distintas = len({f["orden"] for f in filas})
    ws["D9"] = guias_distintas  # celda de valor de "Total Guias"
    _set_fecha(ws, fecha)

    for i, f in enumerate(filas):
        r = data_start + i
        if r > last_template_row:
            copy_row_style(ws, data_start, r, COL_RANGE[0], COL_RANGE[1])
        ws.cell(r, COL_N).value = i + 1
        ws.cell(r, COL_TIPO).value = f["tipo"]
        ws.cell(r, COL_GUIA).value = _num_or_str(f["orden"])
        ws.cell(r, COL_SKU).value = _num_or_str(f["sku"])
        ws.cell(r, COL_DESC).value = f["desc"]

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return {
        "xlsx_bytes": buf.getvalue(),
        "preview": [
            {"N°": i + 1, "Tipo Guia": f["tipo"], "N° Guia": f["orden"],
             "Sku": f["sku"], "Desc. Sku": f["desc"]}
            for i, f in enumerate(filas)
        ],
        "no_encontrados": no_encontrados,
    }


def _set_fecha(ws, fecha: dt.date) -> None:
    """La etiqueta 'Fecha' está en G8 (merged H8:I8 es el valor). Escribe el valor."""
    ws["H8"] = fecha.strftime("%d-%m-%Y")


def _num_or_str(s: str):
    s = str(s).strip()
    if s.isdigit():
        try:
            return int(s)
        except ValueError:
            return s
    return s
