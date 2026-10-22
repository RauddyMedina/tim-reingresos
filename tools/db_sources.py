"""
db_sources.py
=============
Lectores de las pestañas del Google Sheet, indexados por número de entrega para
lookup O(1). Cacheados con st.cache_data (TTL 10 min) cuando corre en Streamlit;
si no hay Streamlit, usa una caché simple en memoria.

Fuentes (verificadas):
  - BASE DE DATOS WMS  (Easy):  D=Entrega, J=Producto(SKU), K=Descripcion, L=Unid
  - BASEDATOSBEETRACK  (fallback Easy): AE=ENTREGA, AJ=Código prod, AK=Nombre prod, AL=Cantidad
  - BASE DATOS PARIS   (Paris): E=Orden, AZ=SKU, BA=Nombre prod, BE='RETORNO'? -> Retiro
"""

from __future__ import annotations

from collections import defaultdict

try:
    import streamlit as st
    _cache = st.cache_data(ttl=600, show_spinner=False)
except Exception:  # sin streamlit (tests / CLI)
    def _cache(fn):
        _store = {}
        def wrap(*a, **k):
            key = (a, tuple(sorted(k.items())))
            if key not in _store:
                _store[key] = fn(*a, **k)
            return _store[key]
        wrap.clear = _store.clear
        return wrap

from tools.auth_sheets import get_service, get_sheet_id

# Pestañas
TAB_WMS = "BASE DE DATOS WMS"
TAB_BEETRACK = "BASEDATOSBEETRACK"
TAB_PARIS = "BASE DATOS PARIS"
TAB_OPL = "BASE DATOS OPL"


def _col(letter: str) -> int:
    """Índice 0-based de una columna por letra (A=0, B=1, ... AZ=51)."""
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch.upper()) - ord("A") + 1)
    return n - 1


def _norm_id(v) -> str:
    """Normaliza un ID de entrega a string sin espacios ni '.0' de floats."""
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _read_values(rng: str) -> list[list]:
    svc = get_service()
    sid = get_sheet_id()
    return (
        svc.spreadsheets().values()
        .get(spreadsheetId=sid, range=rng, valueRenderOption="UNFORMATTED_VALUE")
        .execute()
        .get("values", [])
    )


@_cache
def read_wms() -> dict[str, list[dict]]:
    """{entrega: [{'sku','desc','unid'}, ...]} desde BASE DE DATOS WMS."""
    # Solo se usan D, J, K, L → leer hasta L (recortar a la derecha reduce memoria/payload).
    rows = _read_values(f"'{TAB_WMS}'!A2:L")
    iD, iJ, iK, iL = _col("D"), _col("J"), _col("K"), _col("L")
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        def g(i):
            return r[i] if len(r) > i else ""
        ent = _norm_id(g(iD))
        if not ent:
            continue
        try:
            unid = float(g(iL)) if str(g(iL)).strip() != "" else 0
        except (ValueError, TypeError):
            unid = 0
        out[ent].append({
            "sku": _norm_id(g(iJ)),
            "desc": str(g(iK)).strip(),
            "unid": unid,
        })
    return dict(out)


@_cache
def read_beetrack() -> dict[str, list[dict]]:
    """{entrega: [{'sku','desc','unid'}, ...]} desde BASEDATOSBEETRACK (fallback Easy).

    Clave: col A (Orden). SKU=AJ, Desc=AK, Qty=AL (formato "N / N" → primer número).
    """
    # Solo se usan A, AJ, AK, AL → leer hasta AL (recortar a la derecha reduce memoria/payload).
    rows = _read_values(f"'{TAB_BEETRACK}'!A2:AL")
    iE, iAJ, iAK, iAL = _col("A"), _col("AJ"), _col("AK"), _col("AL")
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        def g(i):
            return r[i] if len(r) > i else ""
        ent = _norm_id(g(iE))
        if not ent:
            continue
        qty_raw = str(g(iAL)).strip()
        try:
            # Formato puede ser "1 / 1" (entregado/total) o número simple
            unid = float(qty_raw.split("/")[0].strip()) if qty_raw else 0
        except (ValueError, TypeError):
            unid = 0
        out[ent].append({
            "sku": _norm_id(g(iAJ)),
            "desc": str(g(iAK)).strip(),
            "unid": unid,
        })
    return dict(out)


@_cache
def read_paris() -> dict[str, list[dict]]:
    """{orden: [{'sku','desc','retorno'(bool)}, ...]} desde BASE DATOS PARIS.

    sku=AZ, desc=BA, retorno = (BE == 'RETORNO').
    """
    # Solo se usan E, AZ, BA, BE → leer hasta BE (recortar a la derecha reduce memoria/payload).
    rows = _read_values(f"'{TAB_PARIS}'!A2:BE")
    iE, iAZ, iBA, iBE = _col("E"), _col("AZ"), _col("BA"), _col("BE")
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        def g(i):
            return r[i] if len(r) > i else ""
        orden = _norm_id(g(iE))
        if not orden:
            continue
        be = str(g(iBE)).strip().upper()
        out[orden].append({
            "sku": str(g(iAZ)).strip(),
            "desc": str(g(iBA)).strip(),
            "retorno": be == "RETORNO",
        })
    return dict(out)


def clear_caches() -> None:
    for fn in (read_wms, read_beetrack, read_paris):
        try:
            fn.clear()
        except Exception:
            pass


@_cache
def read_opl() -> dict[str, list[dict]]:
    """{codigo: [{'sku','desc','unid','local'}, ...]} desde BASE DATOS OPL.

    Se indexa por los DOS codigos que identifican un pedido de OPL, porque el dueno
    tiene a mano cualquiera de los dos segun de donde lo copie:
      - col B 'Suborden'   -> es la que llega a Beetrack como orden
      - col C 'Id entrega' -> NO existe en ninguna otra base, y por eso el generador
                              de TIM contestaba "sin datos en las bases" (22-10).

    'local' (col T) viene de la TIENDA del PDF de EasyGo: sirve para saber a que OPL
    vuelve el reingreso.
    """
    # Solo se usan B, C, J, K, L y T.
    return indexar_opl(_read_values(f"'{TAB_OPL}'!A2:T"))


def indexar_opl(rows: list[list]) -> dict[str, list[dict]]:
    """La parte pura de read_opl, para poder probarla sin red."""
    iB, iC, iJ, iK, iL, iT = (_col("B"), _col("C"), _col("J"),
                              _col("K"), _col("L"), _col("T"))
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        def g(i):
            return r[i] if len(r) > i else ""
        try:
            unid = float(g(iL)) if str(g(iL)).strip() != "" else 0
        except (ValueError, TypeError):
            unid = 0
        linea = {"sku": _norm_id(g(iJ)), "desc": str(g(iK)).strip(),
                 "unid": unid, "local": str(g(iT)).strip()}
        # La MISMA linea queda bajo las dos claves: pegar una u otra da el mismo TIM.
        for clave in (_norm_id(g(iB)), _norm_id(g(iC))):
            if clave:
                out[clave].append(linea)
    return dict(out)
