# Workflow: Generar TIM Easy (Devolución Logística Inversa)

## Objetivo
Producir el Excel TIM de Easy a partir de números de entrega, completando
COD. PRODUCTO, DESCRIPCION y UN automáticamente.

## Inputs
- Lista de **DOCUMENTO ASOCIADO** (números de entrega).
- Fecha del documento (default: hoy).

## Fuente de datos
- Pestaña **`BASE DE DATOS WMS`** del Google Sheet:
  - `D = Entrega` (clave de búsqueda)
  - `J = Producto` → COD. PRODUCTO (SKU)
  - `K = Descripcion` → DESCRIPCION
  - `L = Unid` → UN (se **suma** por SKU dentro de la misma entrega)
- Fallback: si la entrega no está en WMS, se busca en **`BASEDATOSBEETRACK`**
  (`A=Orden` (clave de búsqueda), `AJ=Código del producto`, `AK=Nombre del producto`,
  `AL=Cantidad` — puede venir en formato `"N / N"`, se toma el primer número).
  Nota: la columna `AE` (ENTREGA) suele estar vacía; la clave real es `A` (Orden).

## Reglas
- Una fila por (entrega, SKU); las unidades del mismo SKU se suman.
- Columnas **Motivo Registro, Tipo, Cobro, Observaciones** quedan en blanco
  (llenado manual). La hoja incluye la leyenda de Motivo (1–10) y Tipo (1–3).
- IDs sin datos se reportan como "no encontrados" y no se incluyen.

## Tool
`tools/tim_easy.build_easy(ids, fecha)` → `{xlsx_bytes, preview, no_encontrados}`.
Usa la plantilla `templates/tim_easy_template.xlsx` (preserva logos/estilos).

## Salida
Excel descargable `TIM_Easy_<fecha>.xlsx` con el formato original.

## Edge cases / aprendizajes
- Los datos de WMS rotan; entregas viejas pueden no estar → fallback Beetrack +
  reporte de no encontrados.
- Si hay más productos que filas pre-formateadas, el builder copia el estilo de la
  primera fila de datos para extender la tabla.
