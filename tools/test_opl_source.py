"""
Autocheck de la fuente OPL del generador de TIM. Sin red.

    python TimReingresos/tools/test_opl_source.py

Lo que se protege: que los DOS codigos de un pedido de OPL —la SubOrden y el Id
entrega— den el mismo TIM. El 22-10 pegar el Id entrega contestaba "sin datos en las
bases" porque ese numero no existe en WMS ni en Beetrack, solo en BASE DATOS OPL.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools.db_sources import indexar_opl  # noqa: E402


def fila(suborden, entrega, sku, desc, unid, local="Viña"):
    f = [""] * 20
    f[1], f[2], f[9], f[10], f[11], f[19] = (suborden, entrega, sku, desc, unid, local)
    return f


def test_los_dos_codigos_traen_lo_mismo():
    idx = indexar_opl([fila(1880821212, 2919636302, "1188309", "CUÑA", 1)])
    assert idx["1880821212"] == idx["2919636302"], idx
    assert idx["1880821212"][0]["sku"] == "1188309"


def test_un_pedido_de_varias_lineas_las_trae_todas():
    idx = indexar_opl([fila(100, 200, "A", "uno", 1), fila(100, 200, "B", "dos", 2)])
    assert len(idx["100"]) == 2 and len(idx["200"]) == 2


def test_viene_el_local_para_saber_a_que_opl_vuelve():
    idx = indexar_opl([fila(100, 200, "A", "uno", 1, local="Belloto")])
    assert idx["100"][0]["local"] == "Belloto"


def test_una_fila_sin_codigos_no_entra():
    assert indexar_opl([fila("", "", "A", "uno", 1)]) == {}


def test_la_cantidad_vacia_o_rota_vale_cero_y_no_revienta():
    for mala in ("", "x", None):
        idx = indexar_opl([fila(100, 200, "A", "uno", mala)])
        assert idx["100"][0]["unid"] == 0, mala


if __name__ == "__main__":
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for prueba in pruebas:
        prueba()
        print(f"  ok  {prueba.__name__}")
    print(f"\n{len(pruebas)} pruebas OK")
