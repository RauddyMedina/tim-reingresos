# TIM Reingresos — Guía del proyecto

App web para generar los documentos **TIM de reingreso** (clientes **Easy** y **Paris**)
pegando solo los números de entrega / ID. La app completa SKU, descripción y unidades
automáticamente desde el Google Sheet y entrega el **Excel con el formato oficial** listo
para usar. Reemplaza el llenado manual fila por fila.

🔗 **App en producción:** https://tim-reingresos-fluxaia.streamlit.app/

> ⚠️ El link es **público** y usa el token del dueño para leer el Sheet. **No lo difundas
> fuera del equipo.**

---

## 1. Cómo se usa (para el equipo)

1. Abre el link de la app.
2. Elige el **Cliente**: `Easy` o `Paris`.
3. **Pega los números de entrega / ID** en el cuadro (uno por línea; también vale separados
   por coma o espacio).
4. Pulsa **📨 Enviar ID**. El campo se limpia y aparece la **previsualización** de las filas.
5. Revisa la tabla y pulsa **⬇️ Descargar Excel**.
6. Si actualizaste las bases del Sheet hace menos de 10 minutos, usa **🔄 Refrescar datos**
   antes de generar (la app cachea los datos del Sheet 10 min).

Lo que la app completa automáticamente:
- **Easy** (formato *TIM Devolución Logística Inversa*): COD. PRODUCTO, DESCRIPCIÓN y UN.
  *Motivo, Tipo y Observaciones se llenan a mano.*
- **Paris** (formato *Devoluciones RDD*): Tipo Guía, Sku y Desc. Sku. *El resto a mano.*

Los IDs que no estén en las bases se reportan como "no encontrados" y no se incluyen.

---

## 2. Cómo funciona por dentro (arquitectura WAT)

El proyecto separa **interacción/decisión** (la app) de **ejecución determinista** (los
scripts en `tools/`), de modo que el armado del Excel sea consistente y testeable.

```
ID ingresado
   │
   ▼
app.py  ──►  tools/db_sources.py  ──►  Google Sheet (pestañas WMS / Beetrack / Paris)
(Streamlit)        │  (lee e indexa por ID, con caché 10 min)
   │               ▼
   └──►  tools/tim_easy.py  ó  tools/tim_paris.py  ──►  templates/*.xlsx  ──►  Excel descargable
```

| Pieza | Rol |
|-------|-----|
| `app.py` | Interfaz Streamlit (tema cyberpunk) + orquestación. |
| `tools/auth_sheets.py` | Autenticación Google. En la nube usa `st.secrets`; en local usa el `token.json` del proyecto principal. Refresco **headless** (sin abrir browser). |
| `tools/db_sources.py` | Lee las pestañas del Sheet, normaliza e **indexa por ID** para lookup rápido. Caché `st.cache_data(ttl=600)`. |
| `tools/tim_easy.py` | Arma el Excel de Easy sobre `templates/tim_easy_template.xlsx`. Agrupa por SKU sumando unidades. |
| `tools/tim_paris.py` | Arma el Excel de Paris sobre `templates/devoluciones_paris_template.xlsx`. Una fila por línea de producto, dedup por nombre. |
| `tools/tim_common.py` | Utilidades compartidas (parseo de IDs, estilos, headers). |
| `templates/*.xlsx` | Formatos oficiales con logos y estilos (se preservan). |
| `workflows/*.md` | SOPs (instrucciones) de cada generación. |

### Fuentes de datos (Google Sheet)
- **Easy** → pestaña `BASE DE DATOS WMS` (`D=Entrega`, `J=SKU`, `K=Descripción`, `L=Unid`).
  - *Fallback* → `BASEDATOSBEETRACK`: la clave real es la **columna A = Orden**
    (`AJ=código`, `AK=nombre`, `AL=cantidad`, que puede venir como `"N / N"` → se toma el
    primer número). La columna `AE` suele estar vacía.
- **Paris** → pestaña `BASE DATOS PARIS` (`E=Orden`, `AZ=SKU`, `BA=nombre`, `BE=RETORNO`
  → marca "Retiro"; si no, "Entrega").

---

## 3. Qué se hizo (historial y decisiones)

- Se construyó la **app web** sobre la lógica de generación existente y se le aplicó un
  **tema cyberpunk** (misma paleta que la app de Paris) para consistencia visual.
- **Fixes aplicados durante el desarrollo:**
  - Mapeo de columnas Beetrack: la clave de búsqueda es la **columna A (Orden)**, no `AE`.
  - Botón **"Enviar ID"** que limpia el campo y muestra la previsualización en un solo clic
    (patrón callback `on_click` de Streamlit).
  - **Formato del Excel:** `number_format = "0"` para evitar notación científica
    (`3,86E+08`) y re-aseguro de anchos de columna.
  - **Aviso de reparación de Excel** al abrir el archivo: causado por `firstSheet` fuera de
    rango en la plantilla → se normaliza la vista del libro (`firstSheet = 0`).
- **Despliegue:** GitHub + **Streamlit Community Cloud**, con autenticación **headless**
  vía `refresh_token` en `st.secrets`. El repo es **público** (no contiene secretos, solo
  placeholders): Streamlit Cloud lo clona sin permisos especiales. ⚠️ Si se vuelve privado,
  Streamlit pierde acceso y la app muere con "Oh no. Error running app." — para tenerlo
  privado hay que instalar la GitHub App de Streamlit con acceso al repo.

---

## 4. Mantenimiento

- **Token de Google revocado** (la app deja de leer el Sheet): regenera `token.json` en el
  proyecto principal (`py -3.12 tools/auth_google.py`) y pega el **nuevo `refresh_token`**
  en Streamlit → **Manage app → Settings → Secrets**.
- **Cambió el formato oficial del TIM:** regenera las plantillas en `templates/`.
- **Re-desplegar con repo privado:** Streamlit necesita acceso al repo para re-desplegar.
  Si en algún reboot la app deja de actualizarse por ser el repo privado, vuelve a
  autorizar el acceso de Streamlit a repos privados, o haz el repo público temporalmente:
  ```bash
  gh repo edit RauddyMedina/tim-reingresos --visibility public --accept-visibility-change-consequences
  ```
- **Seguridad:** nunca subir `secrets.toml`, `token.json` ni `credentials.json` (ya están
  en `.gitignore`). El link público lee el Sheet con el token del dueño → no difundir.

---

## 5. Correr en local

```powershell
py -3.12 -m pip install -r TimReingresos/requirements.txt
py -3.12 -m streamlit run TimReingresos/app.py
```

En local usa el `token.json` del proyecto principal (no hace falta configurar secrets).
Abre en http://localhost:8501 (o el puerto que indique la consola).

---

📄 Para el detalle paso a paso del despliegue en Streamlit Cloud, ver
[`README_DEPLOY.md`](README_DEPLOY.md).
