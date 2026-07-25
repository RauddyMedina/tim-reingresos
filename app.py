"""
app.py — Generador de TIM Reingresos (Easy / Paris)
===================================================
Interfaz web (Streamlit) para que cualquier persona genere los documentos de
reingreso TIM ingresando solo los números de entrega / ID. El sistema completa
SKU, descripción y unidades (Easy) o tipo de guía, SKU y descripción (Paris)
desde las bases de datos del Google Sheet, y entrega un Excel descargable con el
formato original.

Local:   streamlit run TimReingresos/app.py
Deploy:  Streamlit Community Cloud (ver README_DEPLOY.md)
"""

from __future__ import annotations

import datetime as dt
import sys
import traceback
from pathlib import Path

import streamlit as st

# Asegurar que TimReingresos/ esté en el path para los imports de tools.*
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.tim_easy import build_easy
from tools.tim_paris import build_paris
from tools.tim_common import parse_ids
from tools.auth_sheets import credentials_available
from tools.push_reingresos import push_reingresos
from tools import db_sources

# URL del tablero donde el bodeguero rebaja los reingresos con foto (ver proyecto_reingresos/)
REINGRESOS_URL = "https://rauddymedina.github.io/reingresos-tim/"

st.set_page_config(page_title="TIM Reingresos", page_icon="📦", layout="centered")

# ── Tema cyberpunk (paleta de la app de Paris) ──────────────────────────────
st.markdown(
    """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap');

  /* Fondo + grid/scanlines sutiles */
  .stApp {
    background-color: #0a0a12 !important;
    background-image:
      linear-gradient(rgba(0,255,247,0.025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,43,214,0.025) 1px, transparent 1px),
      linear-gradient(rgba(10,10,18,0) 50%, rgba(0,0,0,0.18) 50%);
    background-size: 40px 40px, 40px 40px, 100% 3px;
    color: #c8d3f5 !important;
  }
  .stApp, .stApp p, .stApp label, .stApp span, .stApp div {
    font-family: 'Share Tech Mono', monospace;
  }
  [data-testid="stHeader"] { background: transparent !important; }
  [data-testid="stToolbar"] { right: 1rem; }

  /* Título con glow neón */
  h1 {
    font-family: 'Orbitron', sans-serif !important;
    font-weight: 900 !important;
    color: #00fff7 !important;
    letter-spacing: 2px;
    text-shadow: 0 0 6px rgba(0,255,247,0.8), 0 0 18px rgba(0,255,247,0.45);
  }
  h2, h3 {
    font-family: 'Orbitron', sans-serif !important;
    color: #ff2bd6 !important;
    text-shadow: 0 0 8px rgba(255,43,214,0.4);
  }
  /* Subtítulo (st.caption) */
  [data-testid="stCaptionContainer"] {
    color: #ff2bd6 !important;
    text-shadow: 0 0 6px rgba(255,43,214,0.35);
  }

  /* Inputs de texto / textarea */
  textarea, input, .stTextInput input, .stDateInput input {
    background-color: #070710 !important;
    color: #c8d3f5 !important;
    border: 1px solid #1f2740 !important;
    border-radius: 6px !important;
    caret-color: #00fff7 !important;
    font-family: 'Share Tech Mono', monospace !important;
  }
  textarea:focus, input:focus {
    border-color: #00fff7 !important;
    box-shadow: 0 0 0 1px #00fff7, 0 0 12px rgba(0,255,247,0.45) !important;
  }

  /* Contenedores de fecha / select */
  [data-baseweb="input"], [data-baseweb="select"] > div {
    background-color: #070710 !important;
    border: 1px solid #1f2740 !important;
  }

  /* Cajas de info / warning / success */
  [data-testid="stAlert"] {
    background-color: #12121f !important;
    border: 1px solid #1f2740 !important;
    border-left: 4px solid #00fff7 !important;
    color: #c8d3f5 !important;
    border-radius: 6px !important;
  }

  /* Botones neón */
  .stButton > button, .stDownloadButton > button {
    background: transparent !important;
    color: #00fff7 !important;
    border: 1px solid #00fff7 !important;
    border-radius: 6px !important;
    font-family: 'Orbitron', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: 1px;
    text-shadow: 0 0 6px rgba(0,255,247,0.6);
    transition: all 0.18s ease-in-out !important;
  }
  .stButton > button:hover, .stDownloadButton > button:hover {
    background: rgba(0,255,247,0.10) !important;
    box-shadow: 0 0 14px rgba(0,255,247,0.55), inset 0 0 10px rgba(0,255,247,0.15) !important;
    color: #aafffb !important;
  }
  /* Botón secundario (Refrescar) en magenta */
  .stButton > button[kind="secondary"] {
    color: #ff2bd6 !important;
    border-color: #ff2bd6 !important;
    text-shadow: 0 0 6px rgba(255,43,214,0.6);
  }
  .stButton > button[kind="secondary"]:hover {
    background: rgba(255,43,214,0.10) !important;
    box-shadow: 0 0 14px rgba(255,43,214,0.55) !important;
    color: #ff8fe9 !important;
  }

  /* Radio Easy/Paris */
  [data-testid="stRadio"] label {
    color: #c8d3f5 !important;
    font-family: 'Orbitron', sans-serif !important;
    letter-spacing: 1px;
  }
  [data-testid="stRadio"] [aria-checked="true"] + div,
  [data-testid="stRadio"] [data-checked="true"] {
    color: #00fff7 !important;
  }

  /* Tabla de preview */
  [data-testid="stDataFrame"] {
    border: 1px solid #1f2740 !important;
    border-radius: 8px;
    box-shadow: 0 0 12px rgba(0,255,247,0.12);
  }
  [data-testid="stDataFrame"] * { font-family: 'Share Tech Mono', monospace !important; }

  hr { border-color: #1f2740 !important; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("📦 Generador de TIM Reingresos")
st.caption("Ingresa los números de entrega / ID y descarga el documento con el formato listo.")

# Chequeo temprano (sin red): si no hay credenciales configuradas, avisar claramente en vez de
# fallar de forma críptica al primer uso. En Cloud esto significa que faltan los Secrets.
if not credentials_available():
    st.error(
        "⚠️ La app no encuentra credenciales de Google.\n\n"
        "En **Streamlit Cloud**: ve a *Manage app → Settings → Secrets* y carga el bloque "
        "`[gcp_service_account]` (la cuenta de servicio) y `GOOGLE_SHEET_ID`.\n\n"
        "Detalles en `README_DEPLOY.md`."
    )
    st.stop()


def on_enviar():
    """Genera el TIM y limpia el campo de IDs (callback: corre antes del rerender)."""
    raw = st.session_state.get("ids_input", "")
    ids = parse_ids(raw)
    if not ids:
        st.session_state.resultado = {"error": "No ingresaste ninguna ID."}
        return
    fecha = st.session_state.get("fecha_input", dt.date.today())
    cliente = st.session_state.get("cliente", "Easy")
    try:
        res = build_easy(ids, fecha) if cliente == "Easy" else build_paris(ids, fecha)
        res["n_ids"] = len(ids)
        res["cliente"] = cliente
        res["fecha"] = fecha
        st.session_state.resultado = res
    except Exception as e:  # noqa: BLE001
        st.session_state.resultado = {"error": str(e), "trace": traceback.format_exc()}
    # Limpiar el campo (permitido dentro de un callback)
    st.session_state.ids_input = ""


cliente = st.radio("Cliente", ["Easy", "Paris"], horizontal=True, key="cliente")

ayuda = {
    "Easy": "Pega los **DOCUMENTO ASOCIADO** (entregas). Se completan COD. PRODUCTO, "
            "DESCRIPCION y UN. Motivo, Tipo y Observaciones se llenan a mano.",
    "Paris": "Pega los **N° de Guía** (Orden). Se completan Tipo Guía, Sku y Desc. Sku. "
             "El resto del formato se llena a mano.",
}
st.info(ayuda[cliente])

col1, col2 = st.columns([3, 1])
with col1:
    st.text_area(
        "Números de entrega / ID",
        height=180,
        key="ids_input",
        placeholder="Uno por línea (también vale separados por coma o espacio):\n66786745\n66776367",
    )
with col2:
    st.date_input("Fecha", value=dt.date.today(), format="DD/MM/YYYY", key="fecha_input")
    st.write("")
    if st.button("🔄 Refrescar datos", help="Limpia la caché y vuelve a leer el Sheet"):
        db_sources.clear_caches()
        st.success("Caché limpiada.")

ids = parse_ids(st.session_state.get("ids_input", ""))
st.caption(f"{len(ids)} ID(s) detectado(s).")

st.button("📨 Enviar ID", type="primary", on_click=on_enviar)

res = st.session_state.get("resultado")
if res:
    if res.get("error"):
        st.error(res["error"])
        if res.get("trace"):
            with st.expander("🛠️ Detalle técnico (para diagnóstico)"):
                st.code(res["trace"], language="text")
    else:
        preview = res["preview"]
        no_enc = res["no_encontrados"]

        if no_enc:
            st.warning(
                f"{len(no_enc)} ID(s) sin datos en las bases (no se incluyeron): "
                + ", ".join(no_enc)
            )

        if preview:
            st.success(
                f"{len(preview)} fila(s) generadas para "
                f"{res['n_ids'] - len(no_enc)} entrega(s)."
            )
            st.dataframe(preview, use_container_width=True, hide_index=True)

            nombre = f"TIM_{res['cliente']}_{res['fecha'].strftime('%Y-%m-%d')}.xlsx"
            st.download_button(
                "⬇️ Descargar Excel",
                data=res["xlsx_bytes"],
                file_name=nombre,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )

            if st.button("📤 Enviar a reingresos", help="Manda estas filas al tablero donde el bodeguero las rebaja con foto"):
                try:
                    n = push_reingresos(res["cliente"], res["fecha"], preview)
                    st.success(
                        f"{n} línea(s) enviadas al tablero de reingresos. "
                        f"Ábrelo en [{REINGRESOS_URL}]({REINGRESOS_URL})."
                    )
                except Exception as e:  # noqa: BLE001
                    st.error(f"No se pudo enviar a reingresos: {e}")
        else:
            st.error("No se generó ninguna fila. Revisa los IDs ingresados.")
