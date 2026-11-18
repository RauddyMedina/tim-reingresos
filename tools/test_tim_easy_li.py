"""Checks del TIM en el formato nuevo (Formato TIM LI). Sin frameworks ni red.

Uso (desde TimReingresos/): python tools/test_tim_easy_li.py

Cubre lo que se rompe en silencio:
  - el cambio en UNA linea, con el 29... en 'ID Entrega' y el 38... en 'ID retiro';
  - que las listas desplegables, el logo y el sello de Cencosud sobrevivan a la escritura;
  - mas de 25 lineas: filas nuevas y el bloque de firmas corrido hacia abajo.
"""
import datetime as dt
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raiz TimReingresos/

import openpyxl  # noqa: E402

from tools.tim_easy import (TEMPLATE, escribir_xlsx,  # noqa: E402
                            partir_documento, tipo_devolucion)

HOY = dt.date(2026, 11, 18)


def hoja(datos: bytes):
    return openpyxl.load_workbook(BytesIO(datos)).worksheets[0]


def xml_hoja(datos: bytes) -> str:
    return zipfile.ZipFile(BytesIO(datos)).read("xl/worksheets/sheet1.xml").decode("utf-8")


# ── Reparto del documento en las dos columnas ────────────────────────────────
assert partir_documento("2919978013 - 385622746") == ("2919978013", "385622746")
assert partir_documento("385622746 - 2919978013") == ("2919978013", "385622746"), \
    "se reparte por el prefijo, no por el orden"
assert partir_documento("2919978013") == ("2919978013", "")
assert partir_documento("385622746") == ("", "385622746")
assert partir_documento("2918000001 - 385000001 - 385000002") == \
    ("2918000001", "385000001\n385000002"), "los dos retiros encadenados van en la celda"
assert tipo_devolucion("2919978013", "385622746") == "ER"
assert tipo_devolucion("", "385622746") == "Retiro"
assert tipo_devolucion("2919978013", "") == "Entrega"
print("OK - reparto entrega/retiro y Tipo Devolucion")

# ── Un TIM con los tres tipos ────────────────────────────────────────────────
filas = [
    # cambio: la entrega y su retiro, en UNA sola linea
    {"entrega": "2919978013 - 385622746", "sku": "1488002",
     "desc": "CAMBIO REFRIGERADOR BOTTOM FREEZER MED270B (2919978013)", "un": 1},
    # retiro suelto
    {"entrega": "385612309", "sku": "385612309",
     "desc": "RETIRO CD CLOSET 8PTAS/4CJ 183X40X177 TABACO", "un": 1},
    # reingreso de una entrega normal, con DOS productos
    {"entrega": "2920066215", "sku": "1234567", "desc": "COCINA GAS 4Q", "un": 1},
    {"entrega": "2920066215", "sku": "7654321", "desc": "CAMPANA 60CM", "un": 2},
]
datos = escribir_xlsx(filas, HOY, transporte="E&S Transportes")
ws = hoja(datos)

assert ws["H2"].value == "18-11-2026", ws["H2"].value
assert ws["H3"].value == "E&S Transportes", ws["H3"].value

esperado = [
    # N°, Tipo,      ID Entrega,    ID retiro,   SKU,        Unid
    (1, "ER", 2919978013, 385622746, 1488002, 1),
    (2, "Retiro", None, 385612309, 385612309, 1),
    (3, "Entrega", 2920066215, None, "1234567\n7654321", "1\n2"),
]
for i, (n, tipo, ent, ret, sku, un) in enumerate(esperado):
    r = 6 + i
    assert ws[f"B{r}"].value == n, (r, ws[f"B{r}"].value)
    assert ws[f"C{r}"].value == tipo, (r, ws[f"C{r}"].value)
    assert ws[f"E{r}"].value == ent, (r, "E", ws[f"E{r}"].value)
    assert ws[f"F{r}"].value == ret, (r, "F", ws[f"F{r}"].value)
    assert ws[f"G{r}"].value == sku, (r, "G", ws[f"G{r}"].value)
    assert ws[f"I{r}"].value == un, (r, "I", ws[f"I{r}"].value)
    # Motivo y Cobro quedan en blanco: uno es el estado fisico y el otro lo pone LI.
    assert ws[f"D{r}"].value in (None, ""), (r, "D", ws[f"D{r}"].value)
    assert ws[f"K{r}"].value in (None, ""), (r, "K", ws[f"K{r}"].value)

assert ws["H6"].value.startswith("CAMBIO REFRIGERADOR"), ws["H6"].value
assert ws["H8"].value == "COCINA GAS 4Q\nCAMPANA 60CM", ws["H8"].value
assert ws["H8"].alignment.wrapText, "la celda apilada necesita ajuste de texto"
assert (ws.row_dimensions[8].height or 0) >= 30, "la fila apilada quedo baja"
# La fila 9 en adelante sigue vacia y numerada, como la plantilla.
assert ws["B9"].value == 4 and ws["C9"].value in (None, ""), "ensucio una fila de mas"
print("OK - tres tipos, cambio en una linea y productos apilados")

# ── Nada de la plantilla se perdio ───────────────────────────────────────────
partes_src = set(zipfile.ZipFile(TEMPLATE).namelist())
partes_out = set(zipfile.ZipFile(BytesIO(datos)).namelist())
assert partes_src == partes_out, f"faltan partes: {sorted(partes_src - partes_out)}"
x = xml_hoja(datos)
assert "INDIRECT(C6)" in x, "se perdio la lista de 'Motivo reingreso'"
assert "x14:dataValidation" in x, "se perdio la lista de 'Tipo Devolucion' (extension x14)"
assert "Datos!$A$1:$C$1" in x, "la lista de Tipo ya no apunta a la hoja Datos"
wb = openpyxl.load_workbook(BytesIO(datos))
assert wb.sheetnames == ["BASE", "INSTRUCCIONES DE LLENADO", "Datos"], wb.sheetnames
print("OK - desplegables, logo, sello y hojas intactos")

# ── Mas de 25 lineas: crecen las filas y bajan las firmas ────────────────────
muchas = [{"entrega": str(2919000000 + i), "sku": str(1000 + i),
           "desc": f"PRODUCTO {i}", "un": 1} for i in range(27)]
grande = escribir_xlsx(muchas, HOY)
ws2 = hoja(grande)
assert ws2["B32"].value == 27, ("la fila 27 no se escribio", ws2["B32"].value)
assert ws2["E32"].value == 2919000026, ws2["E32"].value
x2 = xml_hoja(grande)
assert "D6:D32" in x2, "el rango de 'Motivo' no crecio con las filas nuevas"
assert "C6:C32" in x2, "el rango de 'Tipo' no crecio con las filas nuevas"
assert 'ref="I35:K35"' in x2, "el bloque de firmas no se corrio"
assert ws2["C35"].value == "Firma/ Timbre transporte", ws2["C35"].value
assert ws2["D2"].value == "Devoluciones Easy.cl", "se movio el titulo, que no debia"
print("OK - 27 lineas: filas nuevas y firmas corridas")

print("OK - todos los checks del Formato TIM LI pasaron")
