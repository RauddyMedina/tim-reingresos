"""
auth_sheets.py
==============
Cliente autenticado de Google Sheets (solo lectura) mediante **cuenta de
servicio**. Funciona TANTO en Streamlit Cloud (llave en st.secrets) COMO en
local (archivo service_account.json).

Por qué cuenta de servicio y no OAuth de usuario:
    El flujo OAuth de usuario guardaba un refresh_token en los secrets. Con la
    pantalla de consentimiento en modo "Testing", Google caduca ese token cada
    7 días → el app moría con `invalid_grant: Token has been expired or revoked`.
    La llave de una cuenta de servicio NO caduca, así que esto no vuelve a pasar.

El app SOLO lee el Sheet (3 pestañas), por eso el scope es de solo lectura y a
la cuenta de servicio le basta con acceso de lector al spreadsheet.

Secrets esperados en Streamlit Cloud (st.secrets):
    GOOGLE_SHEET_ID = "..."
    [gcp_service_account]
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
    client_email = "...@....iam.gserviceaccount.com"
    client_id = "..."
    token_uri = "https://oauth2.googleapis.com/token"
    ...

En local, la llave se busca (en este orden):
    1. env GOOGLE_SERVICE_ACCOUNT_FILE
    2. TimReingresos/service_account.json
    3. ../scaneador/service_account.json   (reusa la llave existente)
"""

from __future__ import annotations

import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Raíces para localizar la llave en local.
_THIS_DIR = Path(__file__).resolve().parent          # TimReingresos/tools
_APP_ROOT = _THIS_DIR.parent                          # TimReingresos
_WORKSPACE_ROOT = _APP_ROOT.parent                    # carpeta que contiene TimReingresos/ y scaneador/

# Rutas candidatas para el archivo de cuenta de servicio (orden de prioridad).
_SA_FILE_CANDIDATES = [
    _APP_ROOT / "service_account.json",
    _WORKSPACE_ROOT / "scaneador" / "service_account.json",
]


def _secrets():
    """Devuelve st.secrets si Streamlit está disponible y tiene la llave, si no None."""
    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            return st.secrets
    except Exception:
        pass
    return None


def _sa_file_path() -> Path | None:
    """Ruta a la llave de cuenta de servicio en local, o None si no hay ninguna."""
    env = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if env and Path(env).exists():
        return Path(env)
    for p in _SA_FILE_CANDIDATES:
        if p.exists():
            return p
    return None


def _creds():
    """Credenciales de cuenta de servicio: desde st.secrets (Cloud) o archivo (local)."""
    sec = _secrets()
    if sec is not None:
        info = dict(sec["gcp_service_account"])
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    path = _sa_file_path()
    if path is None:
        raise FileNotFoundError(
            "No hay credenciales de cuenta de servicio: ni st.secrets['gcp_service_account'] "
            f"ni un service_account.json en {[str(p) for p in _SA_FILE_CANDIDATES]}. "
            "En Streamlit Cloud pega el bloque [gcp_service_account] en Settings → Secrets."
        )
    return service_account.Credentials.from_service_account_file(str(path), scopes=SCOPES)


def get_service():
    """Servicio autenticado de Sheets (cloud o local)."""
    return build("sheets", "v4", credentials=_creds(), static_discovery=True)


def credentials_available() -> bool:
    """True si hay de dónde sacar credenciales (secrets en Cloud o archivo SA en local).

    NO hace ninguna llamada de red: solo verifica que exista la fuente. Sirve para mostrar
    un mensaje claro al inicio en vez de fallar de forma críptica al primer uso.
    """
    if _secrets() is not None:
        return True
    return _sa_file_path() is not None


def get_sheet_id() -> str:
    """ID del spreadsheet desde secrets, env, o el default conocido."""
    try:
        import streamlit as st
        if "GOOGLE_SHEET_ID" in st.secrets:
            return st.secrets["GOOGLE_SHEET_ID"]
    except Exception:
        pass
    env = os.getenv("GOOGLE_SHEET_ID")
    if env:
        return env
    # Fallback: .env del workspace (proyecto principal)
    try:
        from dotenv import load_dotenv
        load_dotenv(_WORKSPACE_ROOT / ".env")
        if os.getenv("GOOGLE_SHEET_ID"):
            return os.getenv("GOOGLE_SHEET_ID")
    except Exception:
        pass
    raise RuntimeError("GOOGLE_SHEET_ID no está en secrets ni en el entorno.")
