# TIM Reingresos — Generador web (Easy + Paris)

Interfaz web donde una persona ingresa los **números de entrega / ID** y descarga
el documento TIM con el formato listo. Completa automáticamente los datos desde el
Google Sheet (bases WMS / Beetrack / Paris).

- **Easy** → formato "TIM Devolución Logística Inversa". Completa COD. PRODUCTO,
  DESCRIPCION y UN. (Motivo, Tipo, Observaciones se llenan a mano.)
- **Paris** → formato "Devoluciones RDD". Completa Tipo Guía, Sku y Desc. Sku.
  (El resto se llena a mano.)

## Probar en local

```powershell
py -3.12 -m pip install -r TimReingresos/requirements.txt
py -3.12 -m streamlit run TimReingresos/app.py
```

En local usa la **cuenta de servicio** `service_account.json` (la busca en
`TimReingresos/service_account.json` o, como fallback, en `../scaneador/service_account.json`).
No hace falta configurar secrets. Abre http://localhost:8501.

## Desplegar en Streamlit Community Cloud (link público, no local)

### 1. Subir el código a GitHub
Sube **solo** la carpeta `TimReingresos/` (o el repo completo). El `.gitignore` ya
excluye `token.json`, `credentials.json` y `secrets.toml` — **no deben subirse nunca**.

```powershell
# desde la raíz del proyecto, si aún no es repo git:
git init
git add TimReingresos
git commit -m "TIM Reingresos web app"
git remote add origin https://github.com/<usuario>/<repo>.git
git push -u origin main
```

> **Visibilidad del repo:** el repo es **público** y no contiene secretos (solo
> placeholders) — así Streamlit Cloud lo clona sin permisos especiales. Si lo vuelves
> **privado**, Streamlit pierde acceso y la app cae con "Oh no. Error running app.";
> en ese caso debes instalar la **GitHub App de Streamlit** (github.com → Settings →
> Applications → Installed GitHub Apps) con acceso al repo, y luego Reboot.

### 2. Crear la app en Streamlit Cloud
1. Entra a https://share.streamlit.io → **New app**.
2. Repo: tu repo privado · Branch: `main` · **Main file path**: `TimReingresos/app.py`.
3. (No despliegues aún — primero carga los Secrets.)

### 3. Cargar los Secrets (cuenta de servicio)
En la pantalla de la app → **Settings → Secrets**, pega el `GOOGLE_SHEET_ID` y el
bloque `[gcp_service_account]` (formato TOML). Plantilla en
`.streamlit/secrets.toml.example`:

```toml
GOOGLE_SHEET_ID = "EL_ID_DE_TU_SPREADSHEET"  # el de la URL del Google Sheet

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"
# (+ auth_uri, auth_provider_x509_cert_url, client_x509_cert_url, universe_domain)
```

**De dónde salen los valores**: del archivo `service_account.json` de la cuenta de
servicio. Cada campo del JSON es una línea del bloque TOML.

**Requisito (una sola vez):** la cuenta de servicio (`client_email`) debe tener
acceso de **lector** al spreadsheet. Compártelo desde Google Sheets con ese email.

> **Por qué cuenta de servicio:** antes se usaba un `refresh_token` de OAuth de
> usuario que, con el proyecto en modo *Testing*, caducaba **a los 7 días** y tiraba
> `invalid_grant: Token has been expired or revoked`. La llave de cuenta de servicio
> **no caduca** → el problema no se repite.

### 4. Deploy
Guarda los secrets y pulsa **Deploy**. Quedará un link público (p. ej.
`https://<algo>.streamlit.app`) que puedes compartir con quien necesite generar TIMs.
No necesitan cuenta de Google: la app usa la cuenta de servicio para leer el Sheet.

## Si sale «Oh no. Error running app.»

Esa es la pantalla genérica de Streamlit Cloud cuando **el proceso de la app se cae o no
arranca** (no es un error de la lógica). Cómo diagnosticar, de lo más probable a lo menos:

0. **`Failed to download the sources for repository` en el log** (fue la causa real en
   jun-2026): Streamlit no puede clonar el repo. Pasa cuando el repo se vuelve **privado**
   sin que la GitHub App de Streamlit tenga acceso. Solución: repo público, o instalar la
   GitHub App de Streamlit con acceso al repo (ver nota de visibilidad arriba) + Reboot.
1. **App dormida / cold start (lo más común).** Streamlit Cloud duerme las apps sin tráfico;
   al despertarlas puede mostrar "Oh no" un momento. **Recarga la página (Ctrl+F5)**. Si sigue,
   entra a https://share.streamlit.io → tu app → **Manage app** (abajo a la derecha) →
   **⋮ → Reboot app**. En la mayoría de los casos con esto vuelve.
2. **Mira los logs.** En el mismo panel **Manage app** está el log en vivo. Busca:
   - `ModuleNotFoundError` / error instalando dependencias → problema de entorno (ver punto 3).
   - `Killed` u `Out of memory` → la app superó el límite de RAM (~1 GB) leyendo las bases.
3. **Versión de Python.** El repo trae `.python-version` con `3.12` (la versión probada). Si lo
   borras, Cloud usa la más nueva (3.13) y alguna dependencia puede no instalar → "Oh no".
4. **Auth del Sheet.** Desde jun-2026 se usa **cuenta de servicio** (`[gcp_service_account]`),
   cuya llave **no caduca** — ya no aplica el problema del token OAuth a 7 días. Si igual ves
   `invalid_grant` o `403/PERMISSION_DENIED`, revisa que el bloque esté completo en Secrets y que
   el `client_email` tenga acceso de lector al spreadsheet.

## Notas
- **Caché**: los datos del Sheet se cachean 10 min. El botón "Refrescar datos" limpia
  la caché si acabas de actualizar las bases.
- **Auth**: usa cuenta de servicio (`service_account.json` / bloque
  `[gcp_service_account]` en Secrets). La llave no caduca; solo se rompería si alguien
  borra/rota la cuenta de servicio o le quita el acceso de lector al spreadsheet.
- **Plantillas**: el formato sale de `TimReingresos/templates/*.xlsx` (derivados de los
  ejemplos, con logos y estilos). Si cambia el formato oficial, regenera esas plantillas.
