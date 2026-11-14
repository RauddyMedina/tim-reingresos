"""
Autocheck de la cuarta fuente (hela) del generador de TIM. Sin red: la consulta se
inyecta.

    python TimReingresos/tools/test_hela_source.py

Lo que se protege: que un retiro 38… que todavía no bajó a ninguna planilla se pueda
armar igual. El 13-11-2026 el 385622746 daba "sin datos en las bases" estando en hela
con su SKU, su descripción y su cantidad, y con fecha de salida el 16-11 —o sea que a
BASEDATOSBEETRACK no iba a llegar en días—.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools import hela_source  # noqa: E402
from tools.hela_source import filas_de_hela, read_hela  # noqa: E402

# Tal cual contesta hela para el retiro 385622746 (recortado a lo que se usa).
RESPUESTA = [{"Codigo_pedido": "385622746", "SKU": "1488002", "Cantidad_producto": 1,
              "Operacion": "R", "Fecha_pedido": "2026-11-16",
              "Descripcion_producto": "(Easy Cd) CAMBIO REFRIGERADOR BOTTOM FREEZER MED270B"}]


def _buscar_falso(respuestas):
    """(status, json) de mentira, y además anota por qué códigos se preguntó."""
    pedidos = []

    def buscar(_sesion, cod):
        pedidos.append(cod)
        return (202, respuestas[cod]) if cod in respuestas else (404, None)
    return buscar, pedidos


def test_el_retiro_llega_con_su_sku_y_su_cantidad():
    hela_source._SESION = "sesion de mentira"
    buscar, _ = _buscar_falso({"385622746": RESPUESTA})
    out = read_hela(["385622746"], buscar=buscar)
    assert out["385622746"] == [{"sku": "1488002", "unid": 1.0,
                                 "desc": "CAMBIO REFRIGERADOR BOTTOM FREEZER MED270B"}], out


def test_se_le_saca_el_nombre_del_cliente_que_hela_pega_adelante():
    """En Beetrack las descripciones vienen sin '(Easy Cd)'. El TIM tiene que verse
    igual salga de donde salga el dato."""
    assert filas_de_hela(RESPUESTA)[0]["desc"].startswith("CAMBIO REFRI")
    # pero el N° de la entrega entre paréntesis NO se toca: con él se empareja el cambio
    con_ref = [{"SKU": "1", "Cantidad_producto": 1,
                "Descripcion_producto": "(Easy Cd) CAMBIO LAMPARA (2919987116)"}]
    assert filas_de_hela(con_ref)[0]["desc"] == "CAMBIO LAMPARA (2919987116)"


def test_un_pedido_de_dos_productos_trae_las_dos_lineas():
    dos = [dict(RESPUESTA[0]), dict(RESPUESTA[0], SKU="1436454",
                                    Descripcion_producto="(Easy Cd) BASURERO")]
    assert len(filas_de_hela(dos)) == 2


def test_lo_que_hela_no_tiene_no_inventa_una_fila():
    hela_source._SESION = "sesion de mentira"
    buscar, _ = _buscar_falso({})
    assert read_hela(["999999999"], buscar=buscar) == {}
    assert filas_de_hela(None) == [] and filas_de_hela({"detail": "Not authenticated"}) == []


def test_la_credencial_pegada_adentro_de_otra_seccion_igual_se_encuentra():
    """En TOML, lo que va DESPUÉS de [gcp_service_account] queda adentro de esa tabla.

    El 14-11-2026 las credenciales se pegaron al final del cuadro de Secrets y la app
    las daba por ausentes: desde la pantalla se ve idéntico a no haberlas puesto.
    """
    import types
    falso = types.ModuleType("streamlit")
    previo = sys.modules.get("streamlit")
    try:
        falso.secrets = {"gcp_service_account": {"client_email": "x",
                                                 "HELA_PRUEBA": "la de adentro"}}
        sys.modules["streamlit"] = falso
        assert hela_source._cred("HELA_PRUEBA") == "la de adentro"
        # y la de la raíz sigue mandando sobre la anidada
        falso.secrets = {"HELA_PRUEBA": "la de arriba",
                         "gcp_service_account": {"HELA_PRUEBA": "la de adentro"}}
        assert hela_source._cred("HELA_PRUEBA") == "la de arriba"
        # lo que no está en ningún lado sigue siendo ''
        falso.secrets = {"gcp_service_account": {"client_email": "x"}}
        assert hela_source._cred("HELA_PRUEBA") == ""
    finally:
        if previo is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previo


def test_sin_credenciales_no_se_consulta_nada():
    """Sin HELA_MAIL/HELA_PASS el generador tiene que seguir andando como antes."""
    hela_source._SESION = None
    buscar, pedidos = _buscar_falso({"385622746": RESPUESTA})
    original = hela_source._cred
    hela_source._cred = lambda _nombre: ""
    try:
        assert read_hela(["385622746"], buscar=buscar) == {}
        assert pedidos == [], "no se le puede preguntar a hela sin con qué entrar"
    finally:
        hela_source._cred = original


def test_solo_se_le_pregunta_por_lo_que_falta():
    """Es una llamada de red por número: lo que la planilla ya tiene no se consulta."""
    hela_source._SESION = "sesion de mentira"
    buscar, pedidos = _buscar_falso({"385622746": RESPUESTA})
    read_hela(["385622746"], buscar=buscar)
    assert pedidos == ["385622746"]
    assert read_hela([], buscar=buscar) == {} and pedidos == ["385622746"]


def test_un_token_vencido_se_renueva_una_vez():
    """Streamlit queda levantado días; el token no dura tanto."""
    hela_source._SESION = "sesion vieja"
    estados = [(401, None), (202, RESPUESTA)]

    def buscar(_s, _cod):
        return estados.pop(0)
    hela_source._sesion = lambda: "sesion nueva"
    try:
        assert "385622746" in read_hela(["385622746"], buscar=buscar)
    finally:
        del hela_source._sesion       # vuelve a la función del módulo
        hela_source._SESION = None


if __name__ == "__main__":
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for prueba in pruebas:
        prueba()
        print(f"  ok  {prueba.__name__}")
    print(f"\n{len(pruebas)} pruebas OK")
