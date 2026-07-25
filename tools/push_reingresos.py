"""
push_reingresos.py
===================
Envía las filas de un TIM ya generado a la pestaña `reingresos` del Google
Sheet, de donde las levanta el tablero de reingresos (proyecto_reingresos/)
para que el bodeguero las rebaje con respaldo fotográfico.

Columnas escritas (deben coincidir con lo que lee gas-deploy/Codigo.js del
tablero): cliente | fecha | entrega | sku | producto | un

API:
    push_reingresos(cliente, fecha, preview) -> int  (filas escritas)
"""

from __future__ import annotations

import datetime as dt

from tools.auth_sheets import get_service, get_sheet_id

TAB_REINGRESOS = "reingresos"
HEADER = ["cliente", "fecha", "entrega", "sku", "producto", "un"]

# Nombre de la columna 'preview' según el cliente (ver tim_easy.py / tim_paris.py)
_KEYS = {
    "Easy": {"entrega": "DOCUMENTO ASOCIADO", "sku": "COD. PRODUCTO", "producto": "DESCRIPCION", "un": "UN"},
    "Paris": {"entrega": "N° Guia", "sku": "Sku", "producto": "Desc. Sku", "un": None},
}


def _ensure_tab(svc, sid: str) -> None:
    """Crea la pestaña `reingresos` con su encabezado si todavía no existe.

    Sin esto, el primer envío falla con 400 "Unable to parse range" (la pestaña
    no existe) y, si alguien la crea a mano sin encabezado, doGet() del tablero
    (que salta la fila 1 asumiendo que es header) se comería la primera línea real.
    """
    meta = svc.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties.title").execute()
    titulos = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if TAB_REINGRESOS in titulos:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=sid,
        body={"requests": [{"addSheet": {"properties": {"title": TAB_REINGRESOS}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"'{TAB_REINGRESOS}'!A1:F1",
        valueInputOption="RAW",
        body={"values": [HEADER]},
    ).execute()


def push_reingresos(cliente: str, fecha: dt.date, preview: list[dict]) -> int:
    """Agrega una fila por línea de `preview` a la pestaña `reingresos`. Devuelve cuántas."""
    keys = _KEYS.get(cliente)
    if keys is None:
        raise ValueError(f"Cliente desconocido: {cliente!r}")
    if not preview:
        return 0

    fecha_str = fecha.strftime("%Y-%m-%d")
    filas = [
        [
            cliente,
            fecha_str,
            str(fila[keys["entrega"]]),
            str(fila[keys["sku"]]),
            fila[keys["producto"]],
            fila.get(keys["un"], "") if keys["un"] else "",
        ]
        for fila in preview
    ]

    svc = get_service()
    sid = get_sheet_id()
    _ensure_tab(svc, sid)
    # ponytail: values.append con INSERT_ROWS inserta ARRIBA si la pestaña tiene un
    # filtro básico activo (visto en sync_to_wms_sheet). No le pongas filtro a
    # 'reingresos'; si hiciera falta, cambiar a values.update calculando la última fila.
    svc.spreadsheets().values().append(
        spreadsheetId=sid,
        range=f"'{TAB_REINGRESOS}'!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": filas},
    ).execute()
    return len(filas)
