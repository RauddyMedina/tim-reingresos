"""
auth_sheets.py
==============
Cliente autenticado de Google Sheets que funciona TANTO en Streamlit Cloud
(credenciales en st.secrets) COMO en local (token.json/credentials.json del
proyecto principal).

En el servidor NO se abre browser: solo se refresca el token con el
refresh_token. Por eso el flujo OAuth de usuario sirve headless.

Secrets esperados (st.secrets):
    GOOGLE_SHEET_ID = "..."
    [google]
    client_id = "..."
    client_secret = "..."
    refresh_token = "..."
    token_uri = "https://oauth2.googleapis.com/token"
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"

# Raíz del proyecto principal (un nivel arriba de TimReingresos/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _secrets():
    """Devuelve st.secrets si Streamlit está disponible y tiene secrets, si no None."""
    try:
        import streamlit as st
        # acceder fuerza la carga; si no hay secrets lanza/queda vacío
        if "google" in st.secrets:
            return st.secrets
    except Exception:
        pass
    return None


def _creds_from_secrets(sec) -> Credentials:
    g = sec["google"]
    creds = Credentials(
        token=None,
        refresh_token=g["refresh_token"],
        client_id=g["client_id"],
        client_secret=g["client_secret"],
        token_uri=g.get("token_uri", _TOKEN_URI),
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def _creds_from_local() -> Credentials:
    """Reusa el token.json del proyecto principal (modo local)."""
    token_path = _PROJECT_ROOT / "token.json"
    if not token_path.exists():
        raise FileNotFoundError(
            f"No hay credenciales: ni st.secrets['google'] ni {token_path}. "
            "En local corre primero la autenticación del proyecto principal "
            "(tools/auth_google.py) para generar token.json."
        )
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds


def get_service():
    """Servicio autenticado de Sheets (cloud o local)."""
    sec = _secrets()
    creds = _creds_from_secrets(sec) if sec else _creds_from_local()
    return build("sheets", "v4", credentials=creds, static_discovery=True)


def get_sheet_id() -> str:
    """ID del spreadsheet desde secrets, env, o el default conocido."""
    sec = _secrets()
    if sec and "GOOGLE_SHEET_ID" in sec:
        return sec["GOOGLE_SHEET_ID"]
    env = os.getenv("GOOGLE_SHEET_ID")
    if env:
        return env
    # Fallback: .env del proyecto principal
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
        if os.getenv("GOOGLE_SHEET_ID"):
            return os.getenv("GOOGLE_SHEET_ID")
    except Exception:
        pass
    raise RuntimeError("GOOGLE_SHEET_ID no está en secrets ni en el entorno.")
