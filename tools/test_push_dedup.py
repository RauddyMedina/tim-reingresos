"""Check minimo de filtrar_nuevas (dedup del envio a reingresos). Sin frameworks.

Regresion del incidente 2026-08-22: 4 clicks en "Enviar a reingresos" dejaron 28
lineas en el tablero en vez de 7, y eso bloqueo el boton "Enviar todo" del tablero.

Uso (desde TimReingresos/): python tools/test_push_dedup.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raiz TimReingresos/

from tools.push_reingresos import _clave, filtrar_nuevas

FILA = ["Easy", "2026-08-22", "66786745", "1351417", "COMEDOR 8S CLARICE", "1"]
OTRA = ["Easy", "2026-08-22", "66776367", "1400001", "SOFA CAMA FELICITAS", "2"]

# Sin nada previo, pasa entera.
assert filtrar_nuevas([FILA, OTRA], set()) == [FILA, OTRA]

# El segundo click no reescribe nada: ese era el bug.
ya = {_clave(FILA), _clave(OTRA)}
assert filtrar_nuevas([FILA, OTRA], ya) == []

# Lote mixto: solo entra lo que falta.
assert filtrar_nuevas([FILA, OTRA], {_clave(FILA)}) == [OTRA]

# Dedup DENTRO del propio lote (misma entrega+sku repetida en el preview).
assert filtrar_nuevas([FILA, list(FILA)], set()) == [FILA]

# Lote vacio -> vacio.
assert filtrar_nuevas([], ya) == []

# La misma linea en otra fecha o para otro cliente es una linea distinta.
assert filtrar_nuevas([["Easy", "2026-08-23", *FILA[2:]]], ya) != []
assert filtrar_nuevas([["Paris", *FILA[1:]]], ya) != []

# Sheets puede devolver la fecha como '2026-08-22T00:00:00' o con espacios: misma clave.
assert _clave([" Easy ", "2026-08-22T00:00:00", " 66786745 ", "1351417"]) == _clave(FILA)

# Fila corta (Sheets recorta las celdas vacias de la derecha): no revienta.
assert _clave(["Easy", "2026-08-22"]) == ("Easy", "2026-08-22", "", "")

print("OK test_push_dedup")
