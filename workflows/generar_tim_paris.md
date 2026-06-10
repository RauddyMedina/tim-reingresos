# Workflow: Generar Devoluciones RDD Paris

## Objetivo
Producir el Excel "Devoluciones RDD" de Paris a partir de números de guía (Orden),
completando Tipo Guía, Sku y Desc. Sku automáticamente.

## Inputs
- Lista de **N° de Guía** (= Orden).
- Fecha del documento (default: hoy).

## Fuente de datos
- Pestaña **`BASE DATOS PARIS`** del Google Sheet:
  - `E = Orden` (clave de búsqueda)
  - `AZ` → **Sku** (por el desfase histórico de 1 columna, el header dice
    'SOLICITUD DE ANULACIÓN' pero el dato real es el código del producto)
  - `BA` → **Desc. Sku** (nombre del producto; ya incluye el motivo entre paréntesis)
  - `BE` (header 'SKU') → si vale **`RETORNO`** ⇒ Tipo Guía = **Retiro**; si no ⇒ **Entrega**

## Reglas
- Una fila por línea de producto de la Orden.
- **Dedup**: una Orden trae líneas duplicadas (una con SKU real y otra con un cartonid
  largo tipo `1-6CB627FA3C...`). Se conserva una fila por nombre de producto,
  prefiriendo el SKU real.
- Columnas **Solicitud, Cod. Beetrack, Motivo Rechazo, Cantidad, √** y la cabecera
  (Folio, Movil, Encargado, Local) quedan en blanco (llenado manual).
- "Total Guias" se autocompleta con el nº de guías distintas; la Fecha con la indicada.
- IDs sin datos se reportan como "no encontrados".

## Tool
`tools/tim_paris.build_paris(ids, fecha)` → `{xlsx_bytes, preview, no_encontrados}`.
Usa la plantilla `templates/devoluciones_paris_template.xlsx` (preserva logos/estilos).

## Salida
Excel descargable `TIM_Paris_<fecha>.xlsx` con el formato original.

## Edge cases / aprendizajes
- "RETORNO" aparece en la columna **BE**, no en AZ (verificado: 759 filas en BE).
- Etiquetas de Tipo Guía: usar **"Entrega" / "Retiro"** (no "RECOGIDO", que era de un
  ejemplo manual antiguo).
