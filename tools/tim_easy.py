"""
tim_easy.py
===========
Genera el TIM de Logística Inversa de Easy ("Formato TIM LI" / Devoluciones Easy.cl) a
partir de números de entrega. Fuente: BASE DE DATOS WMS (fallback BASEDATOSBEETRACK,
BASE DATOS OPL y hela).

Una fila por DOCUMENTO: **el cambio va en una sola línea**, con el 29… en `ID Entrega` y
el 38… en `ID retiro`, que es justo lo que pide el formato nuevo. Los productos del
documento van apilados dentro de la celda.

Se rellena todo lo derivable. Quedan en blanco a propósito:
  - **Motivo reingreso**: en un ER/Retiro es el estado físico del producto (Abollado,
    Quebrado, …), que se ve en el andén y no está en ninguna base.
  - **¿Cobro?**: lo llena el equipo de Logística Inversa, dice el instructivo.
Las dos conservan su lista desplegable.

⚠️ El Excel se escribe **sobre el XML de la plantilla**, no con openpyxl: un round-trip de
openpyxl borra la extensión x14 (el desplegable de `Tipo Devolución`, que es el que manda
el de `Motivo` vía INDIRECT), el sello de confidencialidad de Cencosud y la configuración
de impresión. Comprobado contra el archivo original.

API:
    build_easy(ids, fecha) -> dict con:
        'xlsx_bytes', 'preview' (list[dict]), 'no_encontrados'
"""

from __future__ import annotations

import datetime as dt
import re
import zipfile
from io import BytesIO

from tools.db_sources import read_beetrack, read_opl, read_wms
from tools.hela_source import read_hela
from tools.tim_common import TEMPLATES_DIR

TEMPLATE = TEMPLATES_DIR / "tim_easy_li_template.xlsx"
HOJA = "xl/worksheets/sheet1.xml"          # la hoja BASE
ESTILOS = "xl/styles.xml"

# Layout del formato (hoja BASE)
FILA_1 = 6                                 # primera fila de datos
ULTIMA_FILA = 30                           # última pre-formateada (B6..B30 = 1..25)
CAPACIDAD = ULTIMA_FILA - FILA_1 + 1
CELDA_FECHA = "H2"                         # al lado de "Fecha devolución"
CELDA_TRANSPORTE = "H3"                    # al lado de "Transporte"
COL_N, COL_TIPO, COL_MOTIVO = "B", "C", "D"
COL_ENTREGA, COL_RETIRO = "E", "F"
COL_SKU, COL_DESC, COL_UN = "G", "H", "I"

# Los tres valores del desplegable de 'Tipo Devolución' (hoja Datos, A1:C1). Van EXACTOS:
# el desplegable de 'Motivo reingreso' es INDIRECT(C6) y sólo resuelve con estos nombres.
TIPO_CAMBIO, TIPO_RETIRO, TIPO_ENTREGA = "ER", "Retiro", "Entrega"

# "ID asociado al pedido (29 para entregas - 38 para retiros)", dice el instructivo.
PREFIJO_RETIRO = "38"

TRANSPORTE = "E&S Transportes"


def _aggregate(ids: list[str]):
    """Devuelve (filas, no_encontrados). filas: [{'entrega','sku','desc','un'}]."""
    wms = read_wms()
    beet = read_beetrack()
    # Tercera fuente: los pedidos de OPL. El 'Id entrega' (col C de BASE DATOS OPL) no
    # existe en WMS ni en Beetrack, asi que pegarlo daba "sin datos en las bases"
    # aunque la SubOrden del MISMO pedido si se encontrara (22-10).
    opl = read_opl()
    # Cuarta fuente y ULTIMA: hela, y sólo por lo que ninguna planilla encontró. Un
    # retiro 38... nace en hela y tarda días en llegar a Beetrack (ver hela_source.py).
    # Va al final porque es red —una llamada por número— y porque las planillas traen
    # el dato de origen; hela es el parche para lo que todavía no bajó.
    hela = read_hela([e for e in ids if not (wms.get(e) or opl.get(e) or beet.get(e))])
    filas: list[dict] = []
    no_encontrados: list[str] = []

    for ent in ids:
        # OPL antes que Beetrack: para un pedido de OPL, Beetrack trae el dato
        # derivado (SKU vacio o con el otro codigo, y cantidad "0 / 1" que da 0),
        # mientras que OPL tiene el SKU, la descripcion y las unidades de origen.
        lineas = wms.get(ent) or opl.get(ent) or beet.get(ent) or hela.get(ent)
        if not lineas:
            no_encontrados.append(ent)
            continue
        # agrupar por SKU sumando unidades; conservar primera descripción vista
        agg: dict[str, dict] = {}
        orden_sku: list[str] = []
        for ln in lineas:
            sku = ln["sku"]
            if sku not in agg:
                agg[sku] = {"desc": ln["desc"], "un": 0}
                orden_sku.append(sku)
            agg[sku]["un"] += ln.get("unid", 0) or 0
            if not agg[sku]["desc"] and ln["desc"]:
                agg[sku]["desc"] = ln["desc"]
        for sku in orden_sku:
            un = agg[sku]["un"]
            filas.append({
                "entrega": ent,
                "sku": sku,
                "desc": agg[sku]["desc"],
                "un": int(un) if float(un).is_integer() else un,
            })
    return filas, no_encontrados


# Un retiro (cambio anulado) trae en su propia descripción el N° de la entrega
# original entre paréntesis, ej. "CAMBIO COMEDOR 8S CLARICE 136X136X77 (2918619547)".
_REF_RE = re.compile(r"\((\d{6,})\)\s*$")


def _ref_entrega(desc: str) -> str | None:
    """N° de entrega referenciado al final de la descripción de un retiro, si hay."""
    m = _REF_RE.search(desc or "")
    return m.group(1) if m else None


# Palabra suelta: "RECAMBIO FILTRO AGUA" es un producto real, no un retiro.
# Verificado contra las 17.949 descripciones del Sheet: clasifica igual que el
# substring anterior (0 diferencias), pero ya no puede confundirse.
_RETIRO_RE = re.compile(r"\b(CAMBIO|RETIRO)S?\b")


def _es_retiro(desc: str) -> bool:
    # ponytail: heurístico por texto en la descripción (así es como el equipo ya
    # identifica un cambio/retiro a simple vista). Techo: no exige el paréntesis
    # con N° al final, así un "RETIRO CD JAULA" sin N° igual cuenta como retiro
    # (queda suelto en su propia fila, que es lo correcto).
    return bool(_RETIRO_RE.search((desc or "").upper()))


def _por_sku_unico(por_entrega: dict, retiro: dict, usados: set) -> list | None:
    """La entrega del MISMO producto, si en este TIM hay exactamente una.

    Segunda señal, porque la del paréntesis no siempre está: el retiro 385622746 del
    14-11 se llama "CAMBIO REFRIGERADOR BOTTOM FREEZER MED270B", sin el N° de la
    entrega, y salía en una línea aparte. Comparten el SKU 1488002.

    Si hay dos entregas del mismo producto no se adivina: quedan sueltas, que es lo que
    hacía antes.
    """
    candidatas = [(ent, grupo) for ent, grupo in por_entrega.items()
                  if ent != retiro["entrega"] and ent not in usados
                  and any(x["sku"] == retiro["sku"] for x in grupo)]
    return candidatas[0][1] if len(candidatas) == 1 else None


def _merge_cambios(filas: list[dict]) -> list[dict]:
    """Fusiona cada retiro (cambio anulado) con la fila de su entrega original.

    Se emparejan cuando la descripción del retiro referencia OTRA entrega que también
    está en `filas`, o —si no trae esa referencia— cuando hay UNA sola entrega del mismo
    SKU (evita falsos positivos: un retiro que se referencia a sí mismo, o un
    "RETIRO CD ..." que no calza con nada, quedan sueltos como antes).
    La entrega conserva TODAS sus filas (una por SKU); a cada una se le agrega el N° del
    retiro en 'entrega'. Solo cuando la entrega trae un único SKU se le copia la
    descripción del retiro (que es del mismo producto y aporta el "CAMBIO"/"RETIRO" + el
    N° entre paréntesis); con varios SKU se conserva el nombre de cada producto, si no se
    perdería uno y se duplicaría otro.

    La clasificación retiro/entrega se hace UNA sola vez antes de mutar nada: al fusionar
    se sobreescribe la desc del destino con la del retiro, así que reclasificar sobre la
    marcha haría que el destino pareciera retiro, se fusionara consigo mismo y su fila se
    perdiera (pasaba cuando el retiro venía antes que su entrega en la lista).
    """
    clasificadas = [(f, _es_retiro(f["desc"])) for f in filas]
    por_entrega: dict[str, list[dict]] = {}
    for f, retiro in clasificadas:
        if not retiro:
            por_entrega.setdefault(f["entrega"], []).append(f)
    resultado: list[dict] = []
    usados: set = set()           # entregas que ya se llevaron un retiro
    for f, retiro in clasificadas:
        if not retiro:
            resultado.append(f)
            continue
        ref = _ref_entrega(f["desc"])
        objetivo = por_entrega.get(ref) if ref and ref != f["entrega"] else None
        if not objetivo:
            objetivo = _por_sku_unico(por_entrega, f, usados)
        if not objetivo:
            resultado.append(f)  # retiro huérfano/auto-referenciado: queda solo
            continue
        # Dos retiros de la misma entrega se encadenan (siguen siendo UN cambio); el
        # `usados` es sólo para que el emparejado por SKU no se lleve una entrega que
        # ya tiene su retiro por referencia, que es la señal fuerte.
        usados.add(objetivo[0]["entrega"].split(" - ")[0])
        for fila in objetivo:
            fila["entrega"] = f"{fila['entrega']} - {f['entrega']}"
        if len(objetivo) == 1:
            objetivo[0]["desc"] = f["desc"]
    return resultado


def agrupar_por_entrega(filas: list[dict]) -> list[dict]:
    """[{entrega, skus, descs, uns}] — UNA entrada por documento asociado.

    El TIM se llena a mano despues (Motivo y Observaciones son por documento, no por
    producto), asi que repetir la entrega en varias filas obliga a escribir lo mismo
    tres veces. Pedido del dueno el 22-10: una fila por entrega, con los productos
    apilados dentro de la celda.

    Mantiene el orden en que llegaron las filas: el TIM se lee contra el palet.
    """
    out: dict[str, dict] = {}
    for f in filas:
        ent = str(f["entrega"])
        b = out.setdefault(ent, {"entrega": f["entrega"], "skus": [],
                                 "descs": [], "uns": []})
        b["skus"].append(f["sku"])
        b["descs"].append(f["desc"])
        b["uns"].append(f["un"])
    return list(out.values())


def partir_documento(doc: str) -> tuple[str, str]:
    """'2919978013 - 385622746' -> ('2919978013', '385622746'). (entrega, retiro).

    Se reparte por el PREFIJO y no por la posición: `_merge_cambios` arma el texto como
    "entrega - retiro", pero un retiro suelto llega solo y tiene que caer en su columna.

    Una entrega puede traer DOS retiros encadenados ("entrega - r1 - r2"): salen los dos
    en la celda, uno debajo del otro. Quedarse con el primero perdería el otro en
    silencio, y el TIM es el respaldo de lo que vuelve.
    """
    partes = [p.strip() for p in str(doc).split("-") if p.strip()]
    entregas = [p for p in partes if not p.startswith(PREFIJO_RETIRO)]
    retiros = [p for p in partes if p.startswith(PREFIJO_RETIRO)]
    return "\n".join(entregas), "\n".join(retiros)


def tipo_devolucion(entrega: str, retiro: str) -> str:
    """ER (cambio: salió uno y vuelve otro), Retiro (sólo vuelve) o Entrega (reingreso)."""
    if entrega and retiro:
        return TIPO_CAMBIO
    return TIPO_RETIRO if retiro else TIPO_ENTREGA


# ── Escritura sobre el XML de la plantilla ────────────────────────────────────

def _esc(v) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


_FILA_RE = re.compile(r'<row[^>]*?\br="(\d+)"[^>]*?(?:/>|>[\s\S]*?</row>)')
_CELDA_RE = re.compile(r'<c\s([^>]*?)(?:/>|>[\s\S]*?</c>)')


def _estilo_ajustado(estilos: str, base: int) -> tuple[str, int]:
    """Clona el estilo `base` con ajuste de texto y devuelve (xml, índice del nuevo).

    Hace falta para las celdas con varios productos apilados: sin wrapText Excel muestra
    una sola línea y el resto queda escondido.
    """
    m = re.search(r'<cellXfs[^>]*count="(\d+)"[^>]*>([\s\S]*?)</cellXfs>', estilos)
    if not m:
        return estilos, base
    xfs = re.findall(r'<xf\b[^>]*?/>|<xf\b[^>]*?>[\s\S]*?</xf>', m.group(2))
    if base >= len(xfs):
        return estilos, base
    molde = xfs[base]
    attrs = re.match(r"<xf\b([^>]*?)/?>", molde).group(1)
    attrs = re.sub(r'\s*applyAlignment="[^"]*"', "", attrs)
    hijo = re.search(r"<alignment([^>]*?)/?>", molde)
    al = re.sub(r'\s*wrapText="[^"]*"', "", hijo.group(1).rstrip("/")) if hijo else ""
    nuevo = f'<xf{attrs} applyAlignment="1"><alignment{al} wrapText="1"/></xf>'
    cuerpo = m.group(2) + nuevo
    return (estilos.replace(m.group(0),
                            f'<cellXfs count="{len(xfs) + 1}">{cuerpo}</cellXfs>'),
            len(xfs))


def _renumerar(bloque: str, viejo: int, nuevo: int) -> str:
    """La misma fila, corrida a otro número (la fila y las refs de sus celdas)."""
    bloque = re.sub(r'(<row[^>]*?\br=")\d+(")', rf"\g<1>{nuevo}\g<2>", bloque, count=1)
    return re.sub(rf'(<c r="[A-Z]+){viejo}(")', rf"\g<1>{nuevo}\g<2>", bloque)


def _agrandar(xml: str, faltan: int) -> str:
    """Suma `faltan` filas de datos clonando la última, y corre lo de abajo.

    Sin esto un TIM de más de 25 líneas pisaría el bloque de firmas.
    """
    def mover(m):
        n = int(m.group(1))
        return _renumerar(m.group(0), n, n + faltan) if n > ULTIMA_FILA else m.group(0)

    xml = _FILA_RE.sub(mover, xml)
    molde = next(m.group(0) for m in _FILA_RE.finditer(xml)
                 if int(m.group(1)) == ULTIMA_FILA)
    clones = "".join(_renumerar(molde, ULTIMA_FILA, ULTIMA_FILA + 1 + k)
                     for k in range(faltan))
    xml = xml.replace(molde, molde + clones, 1)

    # Lo que apunta a filas de más abajo y no es una fila: las celdas combinadas (el
    # bloque de firmas) y la dimensión de la hoja. Sólo se corre lo que está DEBAJO de
    # los datos; el título D2:E2 se queda donde está.
    def correr(texto: str) -> str:
        return re.sub(r"([A-Z]+)(\d+)",
                      lambda m: m.group(1) + str(int(m.group(2)) + faltan
                                                 if int(m.group(2)) > ULTIMA_FILA
                                                 else int(m.group(2))),
                      texto)

    xml = re.sub(r'<mergeCell ref="[^"]+"/>', lambda m: correr(m.group(0)), xml)
    xml = re.sub(r'<dimension ref="[^"]+"/>', lambda m: correr(m.group(0)), xml)
    # Los rangos de las dos listas desplegables (la normal de 'Motivo' y la x14 de
    # 'Tipo') terminan JUSTO en la última fila, así que no los agarra el corrimiento.
    xml = xml.replace(f"D{FILA_1}:D{ULTIMA_FILA}", f"D{FILA_1}:D{ULTIMA_FILA + faltan}")
    xml = xml.replace(f"C{FILA_1}:C{ULTIMA_FILA}", f"C{FILA_1}:C{ULTIMA_FILA + faltan}")
    return xml


def _escribir(xml: str, celdas: dict) -> str:
    """Pone los valores en las celdas que ya existen, conservando su estilo.

    `celdas[ref] = (valor, numero, estilo)`: `estilo` None mantiene el de la plantilla.
    """
    def cambiar(m):
        attrs = m.group(1)
        ref_m = re.search(r'\br="([A-Z]+\d+)"', attrs)
        ref = ref_m.group(1) if ref_m else ""
        if ref not in celdas:
            return m.group(0)
        valor, numero, estilo = celdas[ref]
        if estilo is None:
            s_m = re.search(r'\bs="(\d+)"', attrs)
            estilo = s_m.group(1) if s_m else "0"
        if valor in ("", None):
            return f'<c r="{ref}" s="{estilo}"/>'
        if numero:
            return f'<c r="{ref}" s="{estilo}"><v>{valor}</v></c>'
        return (f'<c r="{ref}" s="{estilo}" t="inlineStr">'
                f'<is><t xml:space="preserve">{_esc(valor)}</t></is></c>')

    return _CELDA_RE.sub(cambiar, xml)


def _altura(xml: str, fila: int, alto: int) -> str:
    """Deja la fila lo bastante alta para los productos apilados."""
    def ajustar(m):
        if int(m.group(1)) != fila:
            return m.group(0)
        entero = m.group(0)
        corte = entero.index(">") + 1          # sólo la etiqueta <row ...>, no sus celdas
        abre = re.sub(r'\s*(?:ht|customHeight)="[^"]*"', "", entero[:corte])
        return abre.replace("<row", f'<row ht="{alto}" customHeight="1"', 1) + entero[corte:]

    return _FILA_RE.sub(ajustar, xml)


def _numerico(v) -> bool:
    return str(v).strip().isdigit()


def _apilar(valores: list) -> str:
    return "\n".join("" if v is None else str(v) for v in valores)


def escribir_xlsx(filas: list[dict], fecha: dt.date, transporte: str = TRANSPORTE) -> bytes:
    """Los bytes del Excel desde las filas ya resueltas (una por producto).

    Separado de `build_easy` para poder REARMAR un TIM viejo desde `Historial_TIM` sin
    volver a leer las bases. Las bases cambian todos los dias: el historico tiene que
    devolver el documento que se genero ESE dia, no uno nuevo con los datos de hoy.
    """
    # El Excel lleva una fila por DOCUMENTO (productos apilados en la celda); el preview
    # sigue teniendo una linea por producto, que es lo que necesita el tablero de fotos.
    bloques = agrupar_por_entrega(filas)

    with zipfile.ZipFile(TEMPLATE) as z:
        partes = {i.filename: z.read(i.filename) for i in z.infolist()}
        orden = [i.filename for i in z.infolist()]

    xml = partes[HOJA].decode("utf-8")
    estilos = partes[ESTILOS].decode("utf-8")

    faltan = len(bloques) - CAPACIDAD
    if faltan > 0:
        xml = _agrandar(xml, faltan)

    # El estilo de las celdas de datos, con ajuste de texto, para los apilados.
    base = re.search(rf'<c r="{COL_DESC}{FILA_1}"[^>]*?\bs="(\d+)"', xml)
    estilos, s_ajustado = _estilo_ajustado(estilos, int(base.group(1)) if base else 0)

    def celda(valor):
        """Número si es un número; apilado (con ajuste de texto) si trae varias líneas."""
        if "\n" in str(valor):
            return (valor, False, s_ajustado)
        return (valor, _numerico(valor), None)

    celdas = {CELDA_FECHA: (fecha.strftime("%d-%m-%Y"), False, None),
              CELDA_TRANSPORTE: (transporte, False, None)}
    for i, b in enumerate(bloques):
        r = FILA_1 + i
        entrega, retiro = partir_documento(b["entrega"])
        n = len(b["skus"])
        celdas[f"{COL_N}{r}"] = (i + 1, True, None)
        celdas[f"{COL_TIPO}{r}"] = (tipo_devolucion(entrega, retiro), False, None)
        celdas[f"{COL_ENTREGA}{r}"] = celda(entrega)
        celdas[f"{COL_RETIRO}{r}"] = celda(retiro)
        celdas[f"{COL_SKU}{r}"] = celda(_apilar(b["skus"]) if n > 1 else b["skus"][0])
        celdas[f"{COL_DESC}{r}"] = celda(_apilar(b["descs"]) if n > 1 else b["descs"][0])
        celdas[f"{COL_UN}{r}"] = celda(_apilar(b["uns"]) if n > 1 else b["uns"][0])
        lineas = max(n, entrega.count("\n") + 1, retiro.count("\n") + 1)
        if lineas > 1:
            xml = _altura(xml, r, 15 * lineas)

    partes[HOJA] = _escribir(xml, celdas).encode("utf-8")
    partes[ESTILOS] = estilos.encode("utf-8")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre in orden:
            z.writestr(nombre, partes[nombre])
    return buf.getvalue()


def build_easy(ids: list[str], fecha: dt.date | None = None,
               transporte: str = TRANSPORTE) -> dict:
    fecha = fecha or dt.date.today()
    filas, no_encontrados = _aggregate(ids)
    n_antes = len(filas)
    filas = _merge_cambios(filas)
    return {
        "xlsx_bytes": escribir_xlsx(filas, fecha, transporte),
        "preview": [
            {"N°": i + 1, "DOCUMENTO ASOCIADO": f["entrega"], "COD. PRODUCTO": f["sku"],
             "DESCRIPCION": f["desc"], "UN": f["un"]}
            for i, f in enumerate(filas)
        ],
        "no_encontrados": no_encontrados,
        "fusionados": n_antes - len(filas),  # retiros absorbidos por su entrega original
    }
