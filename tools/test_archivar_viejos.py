"""Check minimo de separar(): que se archive lo viejo y NADA mas. Sin frameworks.

Lo caro de equivocarse aca es esconder trabajo pendiente, asi que el check cubre
sobre todo los bordes: el dia del corte NO se archiva, y una fila sin fecha legible
tampoco.

Uso (desde TimReingresos/): python tools/test_archivar_viejos.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raiz TimReingresos/

from tools.archivar_reingresos_viejos import separar

VIEJA = ["Easy", "2026-08-22", "66786745", "1351417", "COMEDOR 8S CLARICE", "1"]
HOY = ["CD", "2026-10-29", "66776367", "1400001", "SOFA CAMA FELICITAS", "2"]
CORTE = "2026-10-29"

quedan, viejas = separar([VIEJA, HOY], CORTE)
assert viejas == [VIEJA], viejas
assert quedan == [HOY], quedan

# El dia del corte se queda: el corte es exclusivo, si no se archivaria lo de hoy.
assert separar([HOY], CORTE)[1] == []

# Sin fecha no se archiva: ante la duda, se queda en la cola.
SIN_FECHA = ["CD", "", "66776367", "1400001", "X", "1"]
assert separar([SIN_FECHA], CORTE) == ([SIN_FECHA], [])

# La fecha puede venir como serial de Sheets (ver iso_fecha), no solo como texto.
SERIAL = ["Easy", 46256, "66786745", "1351417", "COMEDOR", "1"]   # 2026-08-22
assert separar([SERIAL], CORTE)[1][0][1] == "2026-08-22"

# Fila corta (Sheets recorta las celdas vacias del final) no revienta.
assert separar([["CD", "2026-08-01", "123"]], CORTE)[1][0] == ["CD", "2026-08-01", "123", "", "", ""]

print("OK: separar() archiva solo lo anterior al corte.")
