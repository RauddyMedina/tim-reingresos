"""
limpiar_dup_reingresos.py
=========================
Borra las filas repetidas de la pestaña `reingresos`, dejando la PRIMERA de cada
(cliente, fecha, entrega, sku). Limpieza puntual del incidente 2026-08-22: se
apretó "Enviar a reingresos" 4 veces y quedaron 28 líneas en vez de 7, lo que
además bloqueó el tablero (el botón "Enviar todo" exige completar `total` líneas
y las copias nunca se completan).

Con el dedup ya metido en push_reingresos.py esto no debería volver a hacer falta,
pero sirve igual si alguien pega filas al Sheet a mano.

Uso (desde TimReingresos/):
    python tools/limpiar_dup_reingresos.py            # en seco: solo muestra
    python tools/limpiar_dup_reingresos.py --apply    # escribe
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raíz TimReingresos/

from tools.auth_sheets import get_service, get_sheet_id
from tools.push_reingresos import HEADER, TAB_REINGRESOS, _clave, _txt, iso_fecha

RANGO = f"'{TAB_REINGRESOS}'!A2:F"


def _normalizar(fila: list) -> list[str]:
    """Fila a 6 columnas de texto, con la fecha en ISO (ver iso_fecha)."""
    c = [fila[i] if i < len(fila) else "" for i in range(len(HEADER))]
    return [_txt(c[0]), iso_fecha(c[1])] + [_txt(v) for v in c[2:]]


def limpiar(apply: bool = False) -> int:
    """Muestra (y si apply, aplica) la deduplicación. Devuelve cuántas filas sobran."""
    svc = get_service()
    sid = get_sheet_id()

    res = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=RANGO, valueRenderOption="UNFORMATTED_VALUE"
    ).execute()
    filas = [f for f in res.get("values", []) if any(str(c).strip() for c in f)]

    vistas: set[tuple[str, ...]] = set()
    quedan, sobran = [], []
    for f in filas:
        k = _clave(f)
        if k in vistas:
            sobran.append(f)
        else:
            vistas.add(k)
            quedan.append(_normalizar(f))

    print(f"Pestaña '{TAB_REINGRESOS}': {len(filas)} fila(s) de datos.")
    print(f"  quedan: {len(quedan)}")
    print(f"  se borran (repetidas): {len(sobran)}")
    for f in sobran:
        c = _clave(f)
        print(f"    - {c[0]} | {c[1]} | entrega {c[2]} | sku {c[3]}")

    if not sobran:
        print("\nNo hay nada que limpiar.")
        return 0
    if not apply:
        print("\nEn seco. Volvé a correrlo con --apply para escribir.")
        return len(sobran)

    # La tabla ENCOGE, y values.update solo pisa lo que escribe: hay que blanquear la
    # cola con filas vacías. Se hace en UNA sola llamada (no clear + update) para que no
    # exista un instante con la pestaña borrada y los datos todavía sin reescribir.
    # No borra filas de la grilla, así que no toca el formato de la pestaña.
    vacias = [[""] * len(HEADER) for _ in range(len(filas) - len(quedan))]
    svc.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"'{TAB_REINGRESOS}'!A2",
        valueInputOption="RAW",  # fecha y entrega quedan como texto, ver iso_fecha
        body={"values": quedan + vacias},
    ).execute()
    print(f"\nListo: {len(sobran)} fila(s) borrada(s), quedaron {len(quedan)}.")
    return len(sobran)


if __name__ == "__main__":
    limpiar(apply="--apply" in sys.argv)
