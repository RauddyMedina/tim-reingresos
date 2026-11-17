"""
historial_tim.py
================
Deja constancia de **cada TIM generado**, en la pestaña `Historial_TIM` del Sheet.

Por qué hace falta: hasta el 16-11-2026 lo único que dejaba rastro era el botón
"Enviar a reingresos", que escribe en `reingresos` — y esa pestaña es una **cola**, no
un historial: se vacía a medida que el bodeguero rebaja (`Historial_Reingresos`) y el
29-10 se le archivaron 464 líneas a `reingresos_archivadas`. Un TIM que se generaba y
sólo se descargaba no quedaba en NINGUNA parte, así que no había cómo contestar "¿qué
mandé el 5 de noviembre?".

Se escribe al **generar**, no al descargar: `st.download_button` sólo avisa cuando
alguien lo aprieta, y para entonces el TIM ya existe. Si el usuario genera y no baja
nada, el hecho igual quedó.

⚠️ **No deduplica, a propósito.** Generar dos veces el mismo TIM son dos hechos
distintos y el histórico tiene que mostrar los dos, cada uno con su hora: ahí es donde
se ve un reenvío o una corrección. La idempotencia que sí hace falta es la de
`push_reingresos`, que alimenta el tablero del bodeguero y donde un duplicado obliga a
fotografiar dos veces.

API:
    log_tim(cliente, fecha, preview) -> str   (el tim_id que quedó escrito)
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from tools.auth_sheets import get_service, get_sheet_id
# Sólo `_KEYS`, que ya existía. ⚠️ **No pedirle a push_reingresos un nombre NUEVO**:
# Streamlit Cloud recarga el script pero deja los módulos ya importados en sys.modules,
# así que al desplegar los dos juntos el 16-11-2026 este import se encontró con la copia
# VIEJA de push_reingresos y tumbó la app entera con un ImportError (la pantalla roja que
# vio el dueño). Se arregla con un Reboot, pero el app no puede depender de eso.
from tools.push_reingresos import _KEYS

TAB_HISTORIAL = "Historial_TIM"
HEADER = ["tim_id", "generado_el", "cliente", "fecha_tim", "entrega", "sku",
          "producto", "un"]

# El contenedor de Streamlit Cloud corre en UTC: sin esto un TIM de las 21:40 queda
# anotado a las 00:40 del día siguiente y el histórico miente justo en lo que se le
# pregunta (a qué hora se generó y de qué día es).
TZ = ZoneInfo("America/Santiago")


def asegurar_pestana(svc, sid: str) -> None:
    """Crea `Historial_TIM` con su encabezado si todavía no existe.

    ponytail: sí, push_reingresos tiene su propia versión de esto para `reingresos`.
    La copia es a propósito y es el precio de no acoplar los dos módulos en el deploy
    (ver el comentario del import). Son 10 líneas y las dos pestañas son fijas; si
    alguna vez hay una tercera, ahí sí conviene un módulo aparte que las dos importen
    desde el primer despliegue.
    """
    meta = svc.spreadsheets().get(spreadsheetId=sid,
                                  fields="sheets.properties.title").execute()
    if TAB_HISTORIAL in {s["properties"]["title"] for s in meta.get("sheets", [])}:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=sid,
        body={"requests": [{"addSheet": {"properties": {"title": TAB_HISTORIAL}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"'{TAB_HISTORIAL}'!A1:{chr(64 + len(HEADER))}1",
        valueInputOption="RAW",
        body={"values": [HEADER]},
    ).execute()


def nuevo_id(cliente: str, fecha: dt.date, ahora: dt.datetime) -> str:
    """'Easy-20261116-214052'. Legible y ordenable, sin pedirle un correlativo al Sheet.

    Lleva la hora porque la fecha sola no distingue dos TIM del mismo cliente y día,
    que es justamente el caso que hoy no se puede contestar.
    """
    return f"{cliente}-{fecha:%Y%m%d}-{ahora:%H%M%S}"


def filas_de(tim_id: str, generado_el: str, cliente: str, fecha: dt.date,
             preview: list[dict]) -> list[list]:
    """Las filas a escribir. Pura, sin red: es lo que prueba el autocheck.

    Las columnas del preview se llaman distinto en cada cliente y esa tabla ya existe
    en push_reingresos (`_KEYS`): se importa en vez de copiarla, porque dos copias se
    desincronizan el día que un TIM cambie de formato.
    """
    keys = _KEYS.get(cliente)
    if keys is None:
        raise ValueError(f"Cliente desconocido: {cliente!r}")
    fecha_str = fecha.strftime("%Y-%m-%d")
    return [
        [tim_id, generado_el, cliente, fecha_str,
         str(fila.get(keys["entrega"], "")),
         str(fila.get(keys["sku"], "")),
         fila.get(keys["producto"], ""),
         fila.get(keys["un"], "") if keys["un"] else ""]
        for fila in preview
    ]


def log_tim(cliente: str, fecha: dt.date, preview: list[dict],
            ahora: dt.datetime | None = None) -> str:
    """Anota el TIM en `Historial_TIM`. Devuelve el tim_id, o '' si no había filas."""
    if not preview:
        return ""
    ahora = ahora or dt.datetime.now(TZ)
    tim_id = nuevo_id(cliente, fecha, ahora)
    filas = filas_de(tim_id, ahora.strftime("%Y-%m-%d %H:%M:%S"), cliente, fecha, preview)

    svc = get_service()
    sid = get_sheet_id()
    asegurar_pestana(svc, sid)
    # RAW y no USER_ENTERED por lo mismo que push_reingresos: así la fecha queda como
    # texto '2026-11-16' y no como fecha que al releerla vuelve con el formato del
    # locale de la planilla.
    svc.spreadsheets().values().append(
        spreadsheetId=sid,
        range=f"'{TAB_HISTORIAL}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": filas},
    ).execute()
    return tim_id
