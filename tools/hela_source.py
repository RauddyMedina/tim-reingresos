"""
hela_source.py
==============
Cuarta fuente del generador de TIM: lo que hela ya tiene y las planillas todavía no.

Por qué hace falta: un retiro de Easy (38…) **nace en hela** y recién aparece en
BASEDATOSBEETRACK cuando sale en una ruta y alguien sube el export. En el medio, pegarlo
acá contestaba "sin datos en las bases". Caso del 13-11-2026: el retiro 385622746 estaba
en hela con su SKU (1488002), su descripción y su cantidad —y con fecha de salida el
16-11, o sea que a Beetrack no iba a llegar en días— y el TIM no se podía armar.

Se le pregunta a hela **sólo por los números que ninguna planilla encontró**: es una
llamada de red por número, y las planillas ya traen 798 retiros.

Credenciales: `HELA_MAIL` y `HELA_PASS`, las mismas del panel /hela. En Streamlit Cloud
van en Settings → Secrets; en local salen del entorno o del .env del workspace. Sin
ellas esto devuelve {} y el generador funciona exactamente como antes.

⚠️ Cada consulta queda registrada en hela a nombre de ese usuario.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

API = "https://hela.transyanez.cl/api"
API_LOGIN = f"{API}/login"
API_BUSCAR = f"{API}/rutas/buscar/sin_filtro/"
TIMEOUT = 30
OK = 202          # ⚠️ el éxito de buscar/sin_filtro es 202, no 200. 404 = no lo tiene.

# "(Easy Cd) CAMBIO REFRIGERADOR…" → "CAMBIO REFRIGERADOR…". hela le pega adelante el
# nombre del cliente; en Beetrack las descripciones vienen sin eso y el TIM tiene que
# verse igual salga de donde salga. Se exige que adentro NO haya dígitos para no comerse
# un "(2919987116)" que identifica la entrega.
_PREFIJO_CLIENTE = re.compile(r"^\(\s*[^()\d]+\)\s*")

_WORKSPACE = Path(__file__).resolve().parent.parent.parent


def _cred(nombre: str) -> str:
    """Una credencial desde st.secrets (Cloud), el entorno o el .env del workspace.

    Mismo orden que auth_sheets para el Sheet, para que no haya dos reglas distintas.
    """
    try:
        import streamlit as st
        if nombre in st.secrets:
            return str(st.secrets[nombre]).strip()
        # ⚠️ Pegado al final del cuadro de Secrets, queda DENTRO de
        # [gcp_service_account]: en TOML las claves que siguen a un encabezado de tabla
        # pertenecen a esa tabla. Pasó el 14-11-2026 y desde la pantalla se ve idéntico
        # a no haberlo configurado. Se mira un nivel más abajo antes de darlo por
        # ausente; lo correcto sigue siendo ponerlo arriba de todo.
        for seccion in st.secrets.values():
            if hasattr(seccion, "get") and seccion.get(nombre):
                return str(seccion[nombre]).strip()
    except Exception:                                             # noqa: BLE001
        pass
    if (v := os.getenv(nombre, "").strip()):
        return v
    for env in (_WORKSPACE / ".env", _WORKSPACE / "piloto" / ".env"):
        if env.exists():
            for ln in env.read_text(encoding="utf-8", errors="ignore").splitlines():
                if ln.strip().startswith(f"{nombre}="):
                    return ln.split("=", 1)[1].strip()
    return ""


def hay_credenciales() -> bool:
    """Si hay con qué preguntarle a hela. Sin red: sólo mira que estén las dos.

    Existe para que la pantalla lo pueda decir: sin esto, no configurar los secrets se
    ve exactamente igual que un número que hela tampoco tiene.
    """
    return bool(_cred("HELA_MAIL") and _cred("HELA_PASS"))


def filas_de_hela(respuesta) -> list[dict]:
    """[{'sku','desc','unid'}] desde lo que contesta buscar/sin_filtro. Pura, sin red.

    hela guarda **una fila por producto**, igual que las planillas, así que un pedido de
    dos productos vuelve con dos filas y las dos entran.
    """
    if not isinstance(respuesta, list):
        return []
    out = []
    for f in respuesta:
        if not isinstance(f, dict):
            continue
        desc = _PREFIJO_CLIENTE.sub("", str(f.get("Descripcion_producto", "")).strip())
        try:
            unid = float(f.get("Cantidad_producto") or 0)
        except (TypeError, ValueError):
            unid = 0
        out.append({"sku": str(f.get("SKU", "")).strip(), "desc": desc, "unid": unid})
    return out


_SESION = None


def _sesion():
    """Session autenticada, reusada entre consultas. None si no hay con qué entrar."""
    global _SESION
    if _SESION is not None:
        return _SESION
    mail, clave = _cred("HELA_MAIL"), _cred("HELA_PASS")
    if not (mail and clave):
        return None
    import requests
    s = requests.Session()
    try:
        r = s.post(API_LOGIN, json={"mail": mail, "password": clave}, timeout=TIMEOUT)
        d = r.json() if r.ok else {}
    except Exception:                                             # noqa: BLE001
        return None
    tok = d if isinstance(d, str) else next(
        (str(d[k]) for k in ("access_token", "token", "jwt", "Authorization")
         if isinstance(d, dict) and d.get(k)), "")
    if not tok:
        return None
    s.headers["Authorization"] = tok if tok.lower().startswith("bearer ") else f"Bearer {tok}"
    _SESION = s
    return s


def read_hela(ids, buscar=None) -> dict[str, list[dict]]:
    """{id: [{'sku','desc','unid'}]} para los números que hela conoce.

    `buscar(sesion, cod) -> (status, json)` se puede inyectar para probar sin red.
    Nunca levanta: hela caída, sin credenciales o un 404 dejan ese id afuera y el
    generador lo sigue reportando como "sin datos", que es como se comportaba antes.
    """
    global _SESION
    ids = [str(i).strip() for i in ids if str(i).strip()]
    if not ids:
        return {}
    buscar = buscar or _buscar
    s = _sesion()
    if s is None:
        return {}
    out: dict[str, list[dict]] = {}
    for cod in ids:
        estado, cuerpo = buscar(s, cod)
        if estado == 401:
            # El token se venció con el proceso vivo (Streamlit queda levantado días).
            # Se pide uno nuevo UNA vez y se reintenta; si tampoco, se corta.
            _SESION = None
            s = _sesion()
            if s is None:
                break
            estado, cuerpo = buscar(s, cod)
        if estado != OK:
            continue
        if (lineas := filas_de_hela(cuerpo)):
            out[cod] = lineas
    return out


def _buscar(sesion, cod: str):
    """(status, json) de buscar/sin_filtro. (0, None) si la consulta ni salió."""
    try:
        r = sesion.get(API_BUSCAR + cod, timeout=TIMEOUT)
    except Exception:                                             # noqa: BLE001
        return 0, None
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, None
