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
                            motivo_reingreso, partir_documento, tipo_devolucion)

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

# ── Motivo que se puede adelantar ────────────────────────────────────────────
assert motivo_reingreso("Entrega", "Cliente Anula") == "Cliente anula"
assert motivo_reingreso("Entrega", "Sin Moradores") == "Sin moradores 3 intentos"
assert motivo_reingreso("Entrega", "SIn Moradores") == "Sin moradores 3 intentos", "ojo el tipeo"
assert motivo_reingreso("Entrega", "Dirección No Encontrada") == \
    "Dirección o domicilio no corresponde"
assert motivo_reingreso("Entrega", "Dirección Errónea") == \
    "Dirección o domicilio no corresponde"
assert motivo_reingreso("Entrega", "Rechazo por daño") == "Cliente rechaza por daño"
# Lo que no calza con ninguno de los cinco motivos queda en blanco, no se interpreta.
assert motivo_reingreso("Entrega", "Despacho Adelantado") == ""
assert motivo_reingreso("Entrega", "Reingresado CD Cliente") == ""
assert motivo_reingreso("Entrega", "") == ""
# En un cambio o un retiro el motivo es el ESTADO FISICO, que no esta en ninguna base.
assert motivo_reingreso("ER", "Cliente Anula") == ""
assert motivo_reingreso("Retiro", "Sin Moradores") == ""
print("OK - motivo de reingreso")

# ── Un TIM con los tres tipos ────────────────────────────────────────────────
filas = [
    # cambio: la entrega y su retiro, en UNA sola linea
    {"entrega": "2919978013 - 385622746", "sku": "1488002", "subestado": "Cliente Anula",
     "desc": "CAMBIO REFRIGERADOR BOTTOM FREEZER MED270B (2919978013)", "un": 1},
    # retiro suelto
    {"entrega": "385612309", "sku": "1253588", "subestado": "Sin Moradores",
     "desc": "RETIRO CD CLOSET 8PTAS/4CJ 183X40X177 TABACO", "un": 1},
    # reingreso de una entrega normal, con DOS productos
    {"entrega": "2920066215", "sku": "1234567", "desc": "COCINA GAS 4Q", "un": 1,
     "subestado": "Sin Moradores"},
    {"entrega": "2920066215", "sku": "7654321", "desc": "CAMPANA 60CM", "un": 2,
     "subestado": "Sin Moradores"},
    # reingreso cuyo subestado no calza con ningun motivo del formato
    {"entrega": "2920066300", "sku": "9999999", "desc": "ESTUFA", "un": 1,
     "subestado": "Despacho Adelantado"},
]
datos = escribir_xlsx(filas, HOY)
ws = hoja(datos)

assert ws["H2"].value == "18-11-2026", ws["H2"].value
assert ws["H3"].value == "Transportes Yañez", ws["H3"].value

esperado = [
    # N°, Tipo,      Motivo,                     ID Entrega,  ID retiro,  SKU,   Unid
    (1, "ER", None, 2919978013, 385622746, 1488002, 1),
    (2, "Retiro", None, None, 385612309, 1253588, 1),
    (3, "Entrega", "Sin moradores 3 intentos", 2920066215, None, "1234567\n7654321", "1\n2"),
    (4, "Entrega", None, 2920066300, None, 9999999, 1),
]
for i, (n, tipo, motivo, ent, ret, sku, un) in enumerate(esperado):
    r = 6 + i
    assert ws[f"B{r}"].value == n, (r, ws[f"B{r}"].value)
    assert ws[f"C{r}"].value == tipo, (r, ws[f"C{r}"].value)
    assert ws[f"D{r}"].value == motivo, (r, "D", ws[f"D{r}"].value)
    assert ws[f"E{r}"].value == ent, (r, "E", ws[f"E{r}"].value)
    assert ws[f"F{r}"].value == ret, (r, "F", ws[f"F{r}"].value)
    assert ws[f"G{r}"].value == sku, (r, "G", ws[f"G{r}"].value)
    assert ws[f"I{r}"].value == un, (r, "I", ws[f"I{r}"].value)
    # ¿Cobro? lo pone el equipo de LI, dice el instructivo.
    assert ws[f"K{r}"].value in (None, ""), (r, "K", ws[f"K{r}"].value)

assert ws["H6"].value.startswith("CAMBIO REFRIGERADOR"), ws["H6"].value
assert ws["H8"].value == "COCINA GAS 4Q\nCAMPANA 60CM", ws["H8"].value
assert ws["H8"].alignment.wrapText, "la celda apilada necesita ajuste de texto"
assert (ws.row_dimensions[8].height or 0) >= 30, "la fila apilada quedo baja"
# La fila de abajo sigue vacia y numerada, como viene la plantilla.
assert ws["B10"].value == 5 and ws["C10"].value in (None, ""), "ensucio una fila de mas"
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

# ── El SKU de un retiro sale de hela, no del N° de la orden ──────────────────
# Beetrack repite el N° de la orden en su columna de SKU cuando el pedido es un retiro.
# Se reemplazan las fuentes (sin red) para comprobar que se prefiere el de hela.
import tools.tim_easy as te  # noqa: E402

te.read_wms = lambda: {}
te.read_opl = lambda: {}
te.read_beetrack = lambda: {
    "385618138": [{"sku": "385618138", "desc": "REFRIGERADOR SAMSUNG", "unid": 1,
                   "subestado": ""}],
    "2919679179": [{"sku": "1244921", "desc": "PTA SEVILLANA", "unid": 1,
                    "subestado": "Cliente Anula"}],
}
pedidos_a_hela = []


def _hela_falsa(ids):
    pedidos_a_hela.extend(ids)
    return {"385618138": [{"sku": "1306275", "desc": "REFRIGERADOR SAMSUNG", "unid": 1}]}


te.read_hela = _hela_falsa
filas_ag, no_enc = te._aggregate(["385618138", "2919679179"])
assert no_enc == [], no_enc
por_id = {f["entrega"]: f for f in filas_ag}
assert por_id["385618138"]["sku"] == "1306275", \
    f"el retiro quedo con su propio N° como SKU: {por_id['385618138']['sku']}"
assert por_id["2919679179"]["sku"] == "1244921", "la entrega no se toca"
assert "385618138" in pedidos_a_hela, "no se le pregunto a hela por el retiro sin SKU"
assert "2919679179" not in pedidos_a_hela, "no hay que ir a la red por lo que ya tiene SKU"
assert por_id["2919679179"]["subestado"] == "Cliente Anula"
print("OK - el SKU del retiro se toma de hela")

print("OK - todos los checks del Formato TIM LI pasaron")
