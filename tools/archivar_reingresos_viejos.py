"""
archivar_reingresos_viejos.py
=============================
Saca de la cola `reingresos` las lineas viejas que ya nadie va a rebajar (el calce
se hizo en Beetrack y el TIM quedo sin fotografiar) y las guarda en la pestana
`reingresos_archivadas`.

Por que archivar y no borrar: lo que de verdad "ya se rebajo" vive en
Historial_Reingresos. Lo de aca es trabajo que quedo sin hacer, asi que se mueve
en vez de desaparecer, por si alguna linea si hacia falta.

Efecto en el tablero: solo deja de aparecer. Un destino cuyo atraso se archivo
entero (por ejemplo las lineas viejas que dicen 'Easy', el nombre que tenia el CD
antes del 23-10) deja de mostrar boton, que es justamente lo que confundia.

Uso (desde TimReingresos/):
    python tools/archivar_reingresos_viejos.py                      # en seco, corte = hoy
    python tools/archivar_reingresos_viejos.py --antes-de 2026-10-29
    python tools/archivar_reingresos_viejos.py --apply              # escribe
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raiz TimReingresos/

from tools.auth_sheets import get_service, get_sheet_id
from tools.push_reingresos import HEADER, TAB_REINGRESOS, _txt, iso_fecha

TAB_ARCHIVO = "reingresos_archivadas"
HEADER_ARCHIVO = HEADER + ["archivado_el"]
RANGO = f"'{TAB_REINGRESOS}'!A2:F"


def _normalizar(fila: list) -> list[str]:
    """Fila a 6 columnas de texto, con la fecha en ISO (ver iso_fecha)."""
    c = [fila[i] if i < len(fila) else "" for i in range(len(HEADER))]
    return [_txt(c[0]), iso_fecha(c[1])] + [_txt(v) for v in c[2:]]


def separar(filas: list[list], corte: str) -> tuple[list[list[str]], list[list[str]]]:
    """(quedan, viejas) comparando la fecha de la fila con `corte` (ISO, exclusivo).

    Una fila sin fecha legible NO se archiva: ante la duda se queda en la cola, que
    es el lado seguro (archivar de mas esconde trabajo pendiente).
    """
    quedan, viejas = [], []
    for f in filas:
        n = _normalizar(f)
        (viejas if n[1] and n[1] < corte else quedan).append(n)
    return quedan, viejas


def _ensure_archivo(svc, sid: str) -> None:
    """Crea `reingresos_archivadas` con su encabezado si no existe."""
    meta = svc.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties.title").execute()
    if TAB_ARCHIVO in {s["properties"]["title"] for s in meta.get("sheets", [])}:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=sid,
        body={"requests": [{"addSheet": {"properties": {"title": TAB_ARCHIVO}}}]},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"'{TAB_ARCHIVO}'!A1",
        valueInputOption="RAW", body={"values": [HEADER_ARCHIVO]},
    ).execute()


def archivar(corte: str, apply: bool = False) -> int:
    """Muestra (y si apply, aplica) el archivado. Devuelve cuantas filas se mueven."""
    svc = get_service()
    sid = get_sheet_id()

    res = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=RANGO, valueRenderOption="UNFORMATTED_VALUE"
    ).execute()
    filas = [f for f in res.get("values", []) if any(str(c).strip() for c in f)]
    quedan, viejas = separar(filas, corte)

    print(f"Pestana '{TAB_REINGRESOS}': {len(filas)} linea(s).")
    print(f"  se archivan (fecha < {corte}): {len(viejas)}")
    print(f"  quedan en la cola:             {len(quedan)}")

    por_grupo: dict[tuple[str, str], int] = {}
    for f in viejas:
        por_grupo[(f[0], f[1])] = por_grupo.get((f[0], f[1]), 0) + 1
    for (cli, fec), n in sorted(por_grupo.items()):
        print(f"    - {cli:<14} {fec}  {n} linea(s)")

    if not viejas:
        print("\nNo hay nada que archivar.")
        return 0
    if not apply:
        print("\nEn seco. Volve a correrlo con --apply para escribir.")
        return len(viejas)

    # Primero guardar, despues borrar: si el append falla, la cola queda intacta.
    _ensure_archivo(svc, sid)
    hoy = dt.date.today().isoformat()
    svc.spreadsheets().values().append(
        spreadsheetId=sid, range=f"'{TAB_ARCHIVO}'!A1",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [f + [hoy] for f in viejas]},
    ).execute()

    # La tabla ENCOGE y values.update solo pisa lo que escribe: hay que blanquear la
    # cola con filas vacias, en UNA sola llamada (igual que limpiar_dup_reingresos.py)
    # para que no exista un instante con la pestana vacia.
    vacias = [[""] * len(HEADER) for _ in range(len(filas) - len(quedan))]
    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"'{TAB_REINGRESOS}'!A2",
        valueInputOption="RAW",  # fecha y entrega como texto, ver iso_fecha
        body={"values": quedan + vacias},
    ).execute()
    print(f"\nListo: {len(viejas)} linea(s) movida(s) a '{TAB_ARCHIVO}'.")
    return len(viejas)


if __name__ == "__main__":
    corte = dt.date.today().isoformat()
    if "--antes-de" in sys.argv:
        corte = sys.argv[sys.argv.index("--antes-de") + 1]
        dt.date.fromisoformat(corte)  # revienta temprano si viene mal escrita
    archivar(corte, apply="--apply" in sys.argv)
