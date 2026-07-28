"""Check minimo de _merge_cambios (fusion entrega + retiro). Sin frameworks.

Uso (desde TimReingresos/): python tools/test_merge_cambios.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raiz TimReingresos/

from tools.tim_easy import _merge_cambios

# Caso real verificado contra el Sheet (ver plan): entrega 2918619547 (COMEDOR,
# sku real, un=1) + su retiro 385558219 (CAMBIO ..., referencia la entrega).
filas = [
    {"entrega": "2918619547", "sku": "1351417", "desc": "COMEDOR 8S CLARICE 136X136X77", "un": 1},
    {"entrega": "385558219", "sku": "385558219",
     "desc": "CAMBIO COMEDOR 8S CLARICE 136X136X77 (2918619547)", "un": 0},
]
out = _merge_cambios(filas)
assert len(out) == 1, f"esperaba 1 fila fusionada, hay {len(out)}"
f = out[0]
assert f["entrega"] == "2918619547 - 385558219", f["entrega"]
assert f["sku"] == "1351417"  # sku de la ENTREGA, no del retiro
assert f["un"] == 1  # un de la ENTREGA
assert f["desc"] == "CAMBIO COMEDOR 8S CLARICE 136X136X77 (2918619547)"  # desc del RETIRO

# Retiro auto-referenciado (referencia su propio N°, no una entrega distinta): NO fusiona.
filas2 = [{"entrega": "385564520", "sku": "385564520",
           "desc": "CAMBIO SOFA CAMA FELICITAS 145X77X86 GRIS (385564520)", "un": 1}]
out2 = _merge_cambios(filas2)
assert len(out2) == 1 and out2[0]["entrega"] == "385564520", "auto-referenciado no debe fusionar"

# Retiro huérfano sin N° de entrega referenciado: NO fusiona, queda solo.
filas3 = [{"entrega": "385564514", "sku": "385564514", "desc": "RETIRO CD JAULA DE TRANSPORTE XL", "un": 1}]
out3 = _merge_cambios(filas3)
assert len(out3) == 1 and out3[0]["entrega"] == "385564514", "retiro huerfano no debe fusionar"

# Retiro que referencia una entrega que NO vino en la lista: NO fusiona.
filas4 = [{"entrega": "385999999", "sku": "385999999",
           "desc": "CAMBIO ALGO (2918000000)", "un": 1}]
out4 = _merge_cambios(filas4)
assert len(out4) == 1 and out4[0]["entrega"] == "385999999", "referencia sin match no debe fusionar"

# Dos retiros para la misma entrega: se encadenan.
filas5 = [
    {"entrega": "2918000001", "sku": "SKU1", "desc": "PRODUCTO X", "un": 2},
    {"entrega": "385000001", "sku": "385000001", "desc": "CAMBIO PRODUCTO X (2918000001)", "un": 0},
    {"entrega": "385000002", "sku": "385000002", "desc": "CAMBIO PRODUCTO X OTRA VEZ (2918000001)", "un": 0},
]
out5 = _merge_cambios(filas5)
assert len(out5) == 1, f"esperaba 1 fila con 2 retiros encadenados, hay {len(out5)}"
assert out5[0]["entrega"] == "2918000001 - 385000001 - 385000002", out5[0]["entrega"]

# Entrega normal sin retiro asociado: pasa intacta.
filas6 = [{"entrega": "2918111111", "sku": "SKUX", "desc": "PRODUCTO NORMAL", "un": 3}]
out6 = _merge_cambios(filas6)
assert out6 == filas6, "entrega sin retiro debe quedar intacta"

print("OK - todos los checks de _merge_cambios pasaron")
