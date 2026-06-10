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

En local usa el `token.json` del proyecto principal (no hace falta configurar
secrets). Abre http://localhost:8501.

## Desplegar en Streamlit Community Cloud (link público, no local)

### 1. Subir el código a un repo **privado** de GitHub
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

> El repo debe ser **privado**: aunque los secretos no van en el código, las rutas y
> la lógica de negocio no deberían ser públicas.

### 2. Crear la app en Streamlit Cloud
1. Entra a https://share.streamlit.io → **New app**.
2. Repo: tu repo privado · Branch: `main` · **Main file path**: `TimReingresos/app.py`.
3. (No despliegues aún — primero carga los Secrets.)

### 3. Cargar los Secrets
En la pantalla de la app → **Settings → Secrets**, pega esto (formato TOML),
reemplazando los valores con los reales:

```toml
GOOGLE_SHEET_ID = "1tHffZ6xU7dBuqS4w0vPW6H8tBy76uUBCu-XylrylZZo"

[google]
client_id     = "...apps.googleusercontent.com"
client_secret = "..."
refresh_token = "..."
token_uri     = "https://oauth2.googleapis.com/token"
```

**De dónde salen los valores** (en el equipo local, raíz del proyecto principal):
- `client_id` y `client_secret` → del archivo `credentials.json`
  (dentro de `installed.client_id` / `installed.client_secret`).
- `refresh_token` → del archivo `token.json` (campo `refresh_token`).

Para verlos rápido:
```powershell
py -3.12 -c "import json; d=json.load(open('credentials.json'))['installed']; print('client_id=',d['client_id']); print('client_secret=',d['client_secret'])"
py -3.12 -c "import json; print('refresh_token=', json.load(open('token.json'))['refresh_token'])"
```

### 4. Deploy
Guarda los secrets y pulsa **Deploy**. Quedará un link público (p. ej.
`https://<algo>.streamlit.app`) que puedes compartir con quien necesite generar TIMs.
No necesitan cuenta de Google: la app usa tu token para leer el Sheet.

## Notas
- **Caché**: los datos del Sheet se cachean 10 min. El botón "Refrescar datos" limpia
  la caché si acabas de actualizar las bases.
- **Token revocado**: si Google invalida el `refresh_token`, regenéralo en local
  (`py -3.12 tools/auth_google.py` en el proyecto principal) y vuelve a pegar el
  `refresh_token` nuevo en los Secrets de Streamlit.
- **Plantillas**: el formato sale de `TimReingresos/templates/*.xlsx` (derivados de los
  ejemplos, con logos y estilos). Si cambia el formato oficial, regenera esas plantillas.
```
