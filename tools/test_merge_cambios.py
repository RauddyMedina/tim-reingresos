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

# Regresion 2026-08-14: el RETIRO viene ANTES que su entrega en la lista pegada.
# Antes se perdia la fila entera (el destino, ya mutado con la desc del retiro, se
# reclasificaba como retiro y se fusionaba consigo mismo). Caso real del Sheet.
filas7 = [
    {"entrega": "385575125", "sku": "385575125",
     "desc": "CAMBIO COMODA 6CJ GRECCO 120X69X45CM BLANCO (2918937046)", "un": 0},
    {"entrega": "2918937046", "sku": "1492906",
     "desc": "COMODA 6CJ GRECCO 120X69X45CM BLANCO", "un": 1},
]
out7 = _merge_cambios(filas7)
assert len(out7) == 1, f"la fila fusionada se perdio: {out7}"
assert out7[0]["entrega"] == "2918937046 - 385575125", out7[0]["entrega"]
assert out7[0]["sku"] == "1492906"  # sku de la ENTREGA
assert out7[0]["un"] == 1

# Entrega con VARIOS SKU + su cambio: deben aparecer TODOS los SKU, cada uno con su
# propio nombre de producto, y el N° del retiro en las dos filas.
filas8 = [
    {"entrega": "2918037663", "sku": "1304697", "desc": "ESCRITORIO C/3 CAJONES 136X45X75", "un": 1},
    {"entrega": "2918037663", "sku": "1351410", "desc": "CLOSET 6PTS/1CJ/1ZAP 138X40X177", "un": 1},
    {"entrega": "385000003", "sku": "385000003",
     "desc": "CAMBIO ESCRITORIO C/3 CAJONES 136X45X75 (2918037663)", "un": 0},
]
out8 = _merge_cambios(filas8)
assert len(out8) == 2, f"esperaba las 2 filas de SKU, hay {len(out8)}"
assert [f["sku"] for f in out8] == ["1304697", "1351410"], [f["sku"] for f in out8]
assert all(f["entrega"] == "2918037663 - 385000003" for f in out8), [f["entrega"] for f in out8]
# con varios SKU NO se pisa la descripcion: cada producto conserva su nombre
assert out8[0]["desc"] == "ESCRITORIO C/3 CAJONES 136X45X75"
assert out8[1]["desc"] == "CLOSET 6PTS/1CJ/1ZAP 138X40X177"

# "RECAMBIO" es parte del nombre de un producto real, no un retiro: no debe fusionarse
# ni sacar la fila de la lista de destinos.
filas9 = [
    {"entrega": "2918222222", "sku": "9001", "desc": "RECAMBIO FILTRO AGUA 3 ETAPAS", "un": 1},
]
out9 = _merge_cambios(filas9)
assert out9 == filas9, "RECAMBIO es un producto, no un retiro"

# ── agrupar_por_entrega: el Excel lleva UNA fila por documento ────────────────
# Pedido del dueno el 22-10: Motivo, Tipo y Observaciones se llenan a mano y son por
# documento, no por producto, asi que repetir la entrega obligaba a escribir lo mismo
# tres veces. Los productos van apilados dentro de la celda.
from tools.tim_easy import agrupar_por_entrega  # noqa: E402

tres = [
    {"entrega": "2919636302", "sku": "1188309", "desc": "CUNA", "un": 1},
    {"entrega": "2919636302", "sku": "1450137", "desc": "CLIP", "un": 1},
    {"entrega": "2919636302", "sku": "1190545", "desc": "LATEX", "un": 1},
]
b = agrupar_por_entrega(tres)
assert len(b) == 1, b
assert b[0]["skus"] == ["1188309", "1450137", "1190545"], b[0]
assert b[0]["descs"] == ["CUNA", "CLIP", "LATEX"] and b[0]["uns"] == [1, 1, 1]

# Dos entregas = dos filas, y se respeta el orden en que llegaron (el TIM se lee
# contra el palet).
dos = tres + [{"entrega": "111", "sku": "9", "desc": "OTRO", "un": 2}]
b2 = agrupar_por_entrega(dos)
assert [x["entrega"] for x in b2] == ["2919636302", "111"], b2

# Un solo producto sigue siendo una fila simple (se escribe como numero, no apilado).
b3 = agrupar_por_entrega([{"entrega": "7", "sku": "9", "desc": "UNO", "un": 1}])
assert len(b3) == 1 and b3[0]["skus"] == ["9"]

assert agrupar_por_entrega([]) == []

print("OK - agrupar_por_entrega")
print("OK - todos los checks de _merge_cambios pasaron")
