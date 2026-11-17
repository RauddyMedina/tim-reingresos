"""
push_reingresos.py
===================
Envía las filas de un TIM ya generado a la pestaña `reingresos` del Google
Sheet, de donde las levanta el tablero de reingresos (proyecto_reingresos/)
para que el bodeguero las rebaje con respaldo fotográfico.

Columnas escritas (deben coincidir con lo que lee gas-deploy/Codigo.js del
tablero): cliente | fecha | entrega | sku | producto | un

El envío es IDEMPOTENTE: reenviar el mismo TIM no vuelve a escribir las filas (ver
_clave/filtrar_nuevas). Antes no lo era y cada click duplicaba el TIM completo en el
tablero, dejándolo además bloqueado (el botón "Enviar todo" del tablero exige
completar `total` líneas y las copias nunca se completan).

API:
    push_reingresos(cliente, fecha, preview) -> int  (filas NUEVAS escritas)
"""

from __future__ import annotations

import datetime as dt
import re

from tools.auth_sheets import get_service, get_sheet_id
from tools.db_sources import read_opl

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


def _txt(v) -> str:
    """Celda a texto. Sheets devuelve números para las celdas numéricas: una entrega
    escrita con USER_ENTERED vuelve como 66786745 (int) o 66786745.0 (float)."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def iso_fecha(v) -> str:
    """Fecha a texto ISO 'YYYY-MM-DD'.

    Leyendo con UNFORMATTED_VALUE, una celda que Sheets guardó como fecha real vuelve
    como serial (días desde 1899-12-30), no como texto. Convertirlo acá evita depender
    del locale de la planilla, que con FORMATTED_VALUE devolvería '22-08-2026' y
    rompería la comparación contra el '2026-08-22' que escribe la app.
    """
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(v))).isoformat()
    return str(v).strip()[:10]


# "OPL viña", "OPL Belloto", "opl-vina": lo que el dueno escribe a mano dentro de la
# descripcion del producto para dejar la referencia de donde salio el cambio o retiro.
_OPL_EN_TEXTO = re.compile(r"OPL\s*[:\-]?\s*(VI[NÑ]A|BELLOTO)", re.I)


def opl_en_texto(texto) -> str:
    """'Vina' | 'Belloto' | '' segun lo que diga el texto de la descripcion."""
    m = _OPL_EN_TEXTO.search(str(texto))
    if not m:
        return ""
    return "Belloto" if m.group(1).upper() == "BELLOTO" else "Viña"


def opl_por_entrega(preview: list[dict], keys: dict) -> dict[str, str]:
    """{entrega: local} leyendo las descripciones de los productos del preview.

    Los cambios y retiros que salen de un OPL NO estan en 'BASE DATOS OPL' (el OPL no
    los libero, los devuelve), asi que la unica referencia es la que el dueno escribe en
    la descripcion. Una sola linea marcada vale para TODA la entrega: si no, el mismo
    pedido se partiria en dos palets segun que SKU trajera la nota.
    """
    out: dict[str, str] = {}
    for fila in preview:
        local = opl_en_texto(fila.get(keys["producto"], ""))
        if local:
            out.setdefault(_txt(fila[keys["entrega"]]), local)
    return out


def destino_de(entrega, cliente: str, locales: dict, notas: dict | None = None) -> str:
    """A donde vuelve el reingreso: 'OPL Vina' | 'OPL Belloto' | 'CD' | 'Paris'.

    La columna A de la pestana 'reingresos' es la que el tablero de fotos usa para
    AGRUPAR los palets (grupo = cliente + fecha). Si todo lo de OPL dice 'Easy', el
    bodeguero ve un solo palet que mezcla lo que vuelve al CD con lo que vuelve a cada
    OPL, y lo fotografia junto aunque sean tres destinos distintos.

    `notas` (lo escrito a mano en la descripcion) le gana a 'BASE DATOS OPL': es la
    referencia explicita de donde hay que reingresar, y es el unico dato que existe
    para los cambios y retiros.

    El `cliente` que recibe push_reingresos sigue siendo Easy/Paris: eso elige que
    columnas leer del preview. Lo que cambia es lo que se ESCRIBE.
    """
    ident = _txt(entrega)
    local = (notas or {}).get(ident) or (locales.get(ident) or [{}])[0].get("local", "")
    if local:
        return f"OPL {local}"
    # Lo de Easy que no viene de un OPL vuelve al CD, y asi se llama en bodega.
    return "CD" if cliente == "Easy" else cliente


def _clave(fila: list) -> tuple[str, ...]:
    """Identidad de una línea de reingreso: cliente | fecha | entrega | sku.

    Es la MISMA clave que ya usan idsYaRegistrados() y guardarEnHistorial() en el GAS
    del tablero, así que deduplicar acá no inventa una regla nueva: alinea la escritura
    con lo que la lectura siempre dio por único.
    """
    c = [fila[i] if i < len(fila) else "" for i in range(4)]
    return (_txt(c[0]), iso_fecha(c[1]), _txt(c[2]), _txt(c[3]))


def filtrar_nuevas(filas: list[list], existentes: set[tuple[str, ...]]) -> list[list]:
    """Filas cuya clave no está en `existentes`, deduplicando también dentro del lote."""
    vistas = set(existentes)
    nuevas = []
    for f in filas:
        k = _clave(f)
        if k in vistas:
            continue
        vistas.add(k)
        nuevas.append(f)
    return nuevas


def _claves_existentes(svc, sid: str) -> set[tuple[str, ...]]:
    """Claves ya presentes en la pestaña (desde A2: la fila 1 es el encabezado)."""
    res = svc.spreadsheets().values().get(
        spreadsheetId=sid,
        range=f"'{TAB_REINGRESOS}'!A2:D",
        valueRenderOption="UNFORMATTED_VALUE",  # ver iso_fecha(): sin formato del locale
    ).execute()
    return {_clave(f) for f in res.get("values", []) if any(str(c).strip() for c in f)}


def push_reingresos(cliente: str, fecha: dt.date, preview: list[dict]) -> int:
    """Agrega las líneas de `preview` que aún no estén en `reingresos`. Devuelve cuántas."""
    keys = _KEYS.get(cliente)
    if keys is None:
        raise ValueError(f"Cliente desconocido: {cliente!r}")
    if not preview:
        return 0

    fecha_str = fecha.strftime("%Y-%m-%d")
    # ⚠️ Solo afecta a lo que se empuja de ahora en adelante. Las lineas YA guardadas
    # como 'Easy' se quedan asi a proposito: la clave (cliente|fecha|entrega|sku) es la
    # misma que usa el GAS para saber que ya se fotografio, y reescribirlas haria que
    # el bodeguero tenga que volver a fotografiar todo lo ya hecho.
    try:
        locales = read_opl()
    except Exception:  # noqa: BLE001
        locales = {}   # sin los locales se escribe el cliente, como siempre
    notas = opl_por_entrega(preview, keys)
    filas = [
        [
            destino_de(fila[keys["entrega"]], cliente, locales, notas),
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

    # ponytail: leer-y-después-escribir no es atómico. Dos envíos exactamente
    # simultáneos (dos pestañas del navegador) podrían pasar los dos el filtro y
    # duplicar. Ceiling asumido: esta app la usa una persona a la vez. Si algún día
    # deja de ser así, el arreglo es mover el push al GAS y envolverlo en LockService,
    # como ya hace doPost() para Historial_Reingresos.
    nuevas = filtrar_nuevas(filas, _claves_existentes(svc, sid))
    if not nuevas:
        return 0

    # ponytail: values.append con INSERT_ROWS inserta ARRIBA si la pestaña tiene un
    # filtro básico activo (visto en sync_to_wms_sheet). No le pongas filtro a
    # 'reingresos'; si hiciera falta, cambiar a values.update calculando la última fila.
    # RAW (no USER_ENTERED) para que la fecha quede como texto '2026-08-22' y no como
    # fecha que al releerla vuelve con el formato del locale y rompe la clave de dedup.
    svc.spreadsheets().values().append(
        spreadsheetId=sid,
        range=f"'{TAB_REINGRESOS}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": nuevas},
    ).execute()
    return len(nuevas)
