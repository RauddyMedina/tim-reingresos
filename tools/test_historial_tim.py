"""
Autocheck del histórico de TIM. Sin red: el servicio de Sheets se finge.

    python TimReingresos/tools/test_historial_tim.py

Lo que se protege: que quede constancia de CADA TIM generado, con la hora, y que dos
TIM del mismo cliente y día no se pisen — que es justo la pregunta que el histórico
viene a contestar ("¿qué mandé el 5 de noviembre?").
"""

import datetime as dt
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools import historial_tim as HT  # noqa: E402
from tools.historial_tim import HEADER, filas_de, nuevo_id  # noqa: E402
from tools.push_reingresos import ensure_tab  # noqa: E402

FECHA = dt.date(2026, 11, 16)
AHORA = dt.datetime(2026, 11, 16, 21, 40, 52)

EASY = [{"DOCUMENTO ASOCIADO": "2919960584", "COD. PRODUCTO": "1382811",
         "DESCRIPCION": "COMEDOR 6S ANA", "UN": 1}]
PARIS = [{"N° Guia": "87708288", "Sku": "1495307", "Desc. Sku": "BIDON 5 LT"}]


def test_easy_y_paris_leen_su_propia_columna():
    """Cada cliente nombra distinto las columnas del preview; el histórico se ve igual."""
    e = filas_de("T1", "2026-11-16 21:40:52", "Easy", FECHA, EASY)[0]
    assert e == ["T1", "2026-11-16 21:40:52", "Easy", "2026-11-16",
                 "2919960584", "1382811", "COMEDOR 6S ANA", 1], e
    p = filas_de("T2", "2026-11-16 21:40:52", "Paris", FECHA, PARIS)[0]
    assert p == ["T2", "2026-11-16 21:40:52", "Paris", "2026-11-16",
                 "87708288", "1495307", "BIDON 5 LT", ""], p
    # Paris no tiene columna de unidades (_KEYS['Paris']['un'] is None): vacío, no None,
    # porque Sheets escribe 'None' como texto y ensucia la planilla.
    assert p[-1] == "" and len(p) == len(HEADER)


def test_dos_tim_del_mismo_dia_no_se_pisan():
    """Es LA razón de que el id lleve la hora: la fecha sola no los distingue."""
    a = nuevo_id("Easy", FECHA, AHORA)
    b = nuevo_id("Easy", FECHA, AHORA + dt.timedelta(minutes=3))
    assert a == "Easy-20261116-214052", a
    assert a != b and b.startswith("Easy-20261116-")


def test_generar_dos_veces_deja_DOS_registros():
    """A diferencia de push_reingresos, acá NO se deduplica: son dos hechos distintos."""
    escrito = []

    class FakeValues:
        def append(self, **kw):
            escrito.append(kw["body"]["values"])
            return self

        def update(self, **kw):
            return self

        def execute(self):
            return {}

    class FakeSheets:
        def values(self):
            return FakeValues()

        def get(self, **kw):
            return self

        def execute(self):
            return {"sheets": [{"properties": {"title": HT.TAB_HISTORIAL}}]}

    class FakeSvc:
        def spreadsheets(self):
            return FakeSheets()

    previos = (HT.get_service, HT.get_sheet_id)
    HT.get_service, HT.get_sheet_id = (lambda: FakeSvc()), (lambda: "sid")
    try:
        id1 = HT.log_tim("Easy", FECHA, EASY, ahora=AHORA)
        id2 = HT.log_tim("Easy", FECHA, EASY, ahora=AHORA + dt.timedelta(seconds=30))
        assert id1 and id2 and id1 != id2, (id1, id2)
        assert len(escrito) == 2, escrito
        assert escrito[0][0][4] == "2919960584"
        # y un TIM vacío no escribe nada ni inventa un id
        assert HT.log_tim("Easy", FECHA, [], ahora=AHORA) == ""
        assert len(escrito) == 2
    finally:
        HT.get_service, HT.get_sheet_id = previos


def test_la_pestana_se_crea_con_sus_8_columnas():
    """ensure_tab calcula la letra del encabezado: con 8 columnas es A1:H1, no A1:F1."""
    rangos = []

    class FakeValues:
        def update(self, **kw):
            rangos.append(kw["range"])
            return self

        def execute(self):
            return {}

    class FakeSheets:
        def __init__(self, existe):
            self.existe = existe

        def get(self, **kw):
            return self

        def batchUpdate(self, **kw):
            return self

        def values(self):
            return FakeValues()

        def execute(self):
            return {"sheets": [{"properties": {"title": "otra"}}]} if not self.existe \
                else {"sheets": [{"properties": {"title": HT.TAB_HISTORIAL}}]}

    class FakeSvc:
        def __init__(self, existe):
            self.existe = existe

        def spreadsheets(self):
            return FakeSheets(self.existe)

    ensure_tab(FakeSvc(False), "sid", HT.TAB_HISTORIAL, HEADER)
    assert rangos == [f"'{HT.TAB_HISTORIAL}'!A1:H1"], rangos
    # y si ya existe no la vuelve a tocar (borraría el encabezado y las filas de abajo
    # quedarían corridas al leerlas)
    ensure_tab(FakeSvc(True), "sid", HT.TAB_HISTORIAL, HEADER)
    assert len(rangos) == 1, rangos


def test_la_hora_es_de_chile_y_no_la_del_contenedor():
    """Streamlit Cloud corre en UTC: sin zona, un TIM de las 21:40 queda al día siguiente."""
    assert str(HT.TZ) == "America/Santiago"
    chile = dt.datetime.now(HT.TZ)
    assert chile.utcoffset() is not None and chile.utcoffset().days == -1  # -03:00/-04:00


if __name__ == "__main__":
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for prueba in pruebas:
        prueba()
        print(f"  ok  {prueba.__name__}")
    print(f"\n{len(pruebas)} pruebas OK")
