"""
Tablero - Lectura de la base de conocimiento.

Solo lee. Cruza las tres fuentes que produjo el motor:

    gold_standard_86        los 86 municipios y su poblacion (Fase 2)
    discovery_urls_86       donde mirar, con evidencia (Fase 3)
    hallazgos_86            que dicen, con los 5 sellos (Fase 4)

Regla que atraviesa todo el modulo: **ningun dato viaja sin su evidencia**. Cada
valor que sale de aca lleva su cita textual, su URL, su fecha y su confianza. Es
lo que diferencia a MIP de un dashboard cualquiera: un numero que no se puede
abrir hasta la fuente no sirve frente a un intendente ni frente a un auditor.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _r in (PROJECT_ROOT / "src" / "discovery", PROJECT_ROOT / "src" / "impacto"):
    if str(_r) not in sys.path:
        sys.path.insert(0, str(_r))

SQLITE_DISCOVERY = PROJECT_ROOT / "data" / "processed" / "discovery" / "discovery_urls_86.sqlite"
SQLITE_HALLAZGOS = PROJECT_ROOT / "data" / "processed" / "extraction" / "hallazgos_86.sqlite"
SQLITE_OPORTUNIDADES = PROJECT_ROOT / "data" / "processed" / "oportunidades" / "oportunidades_86.sqlite"
SQLITE_GABINETE = PROJECT_ROOT / "data" / "processed" / "gabinete" / "gabinete_86.sqlite"
SQLITE_SEGURIDAD = PROJECT_ROOT / "data" / "processed" / "seguridad" / "seguridad_86.sqlite"
SQLITE_OPERATIVOS = PROJECT_ROOT / "data" / "processed" / "seguridad" / "operativos_86.sqlite"

# Los siete aspectos del eje 2, con su etiqueta legible y en orden de lectura:
# primero lo que el municipio PAGA, despues quien mas interviene, al final lo
# que ocurrio. Un intendente lee su gestion antes que la de la provincia.
ASPECTOS_SEGURIDAD = (
    ("patrulla_urbana", "Patrulla urbana / policía local"),
    ("centro_monitoreo", "Centro de monitoreo / cámaras"),
    ("alarmas_vecinales", "Alarmas vecinales / botón antipánico"),
    ("policia_bonaerense", "Policía Bonaerense"),
    ("fuerzas_federales", "Fuerzas federales"),
    ("operativos", "Operativos de control"),
    ("allanamientos", "Allanamientos"),
)
SQLITE_INDEC = PROJECT_ROOT / "data" / "processed" / "indec" / "censo_2022.sqlite"
SQLITE_TEMAS = PROJECT_ROOT / "data" / "processed" / "temas" / "temas_86.sqlite"

CANALES_DIGITALES = ("web", "whatsapp", "telegram", "app", "email")
CANALES_SIN_DIGITAL = ("telefono", "presencial")


def _conectar(path: Path) -> Optional[sqlite3.Connection]:
    if not Path(path).exists():
        return None
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _filas(path: Path, sql: str, args: tuple = ()) -> List[dict]:
    con = _conectar(path)
    if con is None:
        return []
    try:
        return [dict(f) for f in con.execute(sql, args)]
    except sqlite3.Error:
        return []
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Municipios
# ---------------------------------------------------------------------------


def municipios() -> List[dict]:
    """Los 86, con lo que se sabe de cada uno."""
    from discovery_engine import cargar_municipios

    base = {
        m.nombre: {
            "id_municipio": m.id_municipio,
            "municipio": m.nombre,
            "poblacion": m.poblacion,
            "urls": 0,
            "sitio_oficial": None,
            "sitio_sin_https": None,
            "estado_descubrimiento": "no_procesado",
            "variables_con_evidencia": 0,
            "canal_turnos": None,
        }
        for m in cargar_municipios()
    }

    for f in _filas(
        SQLITE_DISCOVERY,
        "SELECT municipio, total_urls, estado, sitio_sin_https FROM municipios_discovery",
    ):
        if f["municipio"] in base:
            base[f["municipio"]].update(
                urls=f["total_urls"],
                estado_descubrimiento=f["estado"],
                sitio_sin_https=f["sitio_sin_https"],
            )

    for f in _filas(
        SQLITE_DISCOVERY,
        "SELECT municipio, url FROM discovery_urls WHERE tipo = 'sitio_oficial' "
        "GROUP BY municipio",
    ):
        if f["municipio"] in base:
            base[f["municipio"]]["sitio_oficial"] = f["url"]

    for f in _filas(
        SQLITE_HALLAZGOS,
        "SELECT municipio, COUNT(*) n FROM hallazgos WHERE estado = 'verificado' "
        "GROUP BY municipio",
    ):
        if f["municipio"] in base:
            base[f["municipio"]]["variables_con_evidencia"] = f["n"]

    for f in _filas(
        SQLITE_HALLAZGOS,
        "SELECT municipio, valor FROM hallazgos WHERE variable = 'canal_turnos_salud' "
        "AND estado = 'verificado'",
    ):
        if f["municipio"] in base:
            base[f["municipio"]]["canal_turnos"] = f["valor"]

    return sorted(base.values(), key=lambda m: m["municipio"])


def ficha(nombre: str) -> dict:
    """Todo lo que MIP sabe de un municipio, con la evidencia de cada dato."""
    todos = {m["municipio"]: m for m in municipios()}
    if nombre not in todos:
        return {}
    datos = dict(todos[nombre])
    datos["urls_detalle"] = _filas(
        SQLITE_DISCOVERY,
        "SELECT url, tipo, fuente_query, titulo_fragmento, confianza, "
        "estado_validacion, es_oficial, fecha_descubrimiento "
        "FROM discovery_urls WHERE municipio = ? ORDER BY tipo",
        (nombre,),
    )
    datos["hallazgos"] = _filas(
        SQLITE_HALLAZGOS,
        "SELECT variable, valor, detalle, url, fecha, fragmento, tipo_fuente, "
        "confianza, estado, modelo FROM hallazgos WHERE municipio = ? ORDER BY variable",
        (nombre,),
    )
    return datos


# ---------------------------------------------------------------------------
# Vistas de negocio
# ---------------------------------------------------------------------------


def mapa_turnos() -> dict:
    """El mapa comercial: quien ya resolvio, quien no, y de quien no sabemos."""
    filas = _filas(
        SQLITE_HALLAZGOS,
        "SELECT municipio, valor, fragmento, url, confianza FROM hallazgos "
        "WHERE variable = 'canal_turnos_salud' AND estado = 'verificado'",
    )
    poblaciones = {m["municipio"]: m["poblacion"] for m in municipios()}
    con_canal = {f["municipio"] for f in filas}

    def _armar(valores):
        salida = []
        for f in filas:
            if f["valor"] not in valores:
                continue
            salida.append({**f, "poblacion": poblaciones.get(f["municipio"])})
        return sorted(salida, key=lambda x: -(x["poblacion"] or 0))

    return {
        "digitales": _armar(CANALES_DIGITALES),
        "sin_digital": _armar(CANALES_SIN_DIGITAL),
        "sin_datos": sorted(
            [
                {"municipio": m["municipio"], "poblacion": m["poblacion"]}
                for m in municipios()
                if m["municipio"] not in con_canal
            ],
            key=lambda x: -(x["poblacion"] or 0),
        ),
    }


def cola_de_revision() -> List[dict]:
    """Lo que necesita ojo humano antes de ir a una propuesta.

    Dos cosas distintas:
      - citas que el modelo invento y la verificacion tumbo (ADR-0014)
      - hallazgos con evidencia corta, donde la cita es real pero puede no
        sostener la conclusion. Es el limite conocido: la verificacion frena la
        alucinacion, no el error de criterio.
    """
    rechazadas = _filas(
        SQLITE_HALLAZGOS,
        "SELECT municipio, variable, modelo FROM hallazgos WHERE estado = 'cita_rechazada'",
    )
    flojas = _filas(
        SQLITE_HALLAZGOS,
        "SELECT municipio, variable, valor, fragmento, url FROM hallazgos "
        "WHERE estado = 'verificado' AND LENGTH(fragmento) < 45 ORDER BY LENGTH(fragmento)",
    )
    return [
        {**r, "motivo": "cita_rechazada", "detalle": "El modelo cito algo que no estaba en la fuente"}
        for r in rechazadas
    ] + [
        {**f, "motivo": "evidencia_corta", "detalle": "La cita es real pero puede no sostener la conclusion"}
        for f in flojas
    ]


def resumen() -> dict:
    todos = municipios()
    turnos = mapa_turnos()
    urls = _filas(SQLITE_DISCOVERY, "SELECT COUNT(*) n FROM discovery_urls")
    verif = _filas(SQLITE_HALLAZGOS, "SELECT COUNT(*) n FROM hallazgos WHERE estado='verificado'")
    sin_https = [m for m in todos if m["sitio_sin_https"] == 1]
    return {
        "municipios": len(todos),
        "poblacion_total": sum(m["poblacion"] or 0 for m in todos),
        "urls_descubiertas": urls[0]["n"] if urls else 0,
        "con_sitio_oficial": len([m for m in todos if m["sitio_oficial"]]),
        "hallazgos_verificados": verif[0]["n"] if verif else 0,
        "turnos_digitales": len(turnos["digitales"]),
        "turnos_sin_digital": len(turnos["sin_digital"]),
        "turnos_sin_datos": len(turnos["sin_datos"]),
        "sitios_sin_https": [m["municipio"] for m in sin_https],
        "pendientes_revision": len(cola_de_revision()),
    }


SQLITE_TERRITORIO = PROJECT_ROOT / "data" / "processed" / "territorio" / "entidades_86.sqlite"

# Capas del mapa. El orden define el orden de dibujado y el de la leyenda.
CAPAS_MAPA = {
    "Salud": ("hospital", "caps", "clinica_privada", "farmacia"),
    "Educación": ("jardin", "escuela_primaria", "escuela_secundaria", "escuela_especial",
                  "educacion_superior", "escuela_sin_clasificar"),
    "Gobierno y seguridad": ("municipalidad", "delegacion", "concejo_deliberante",
                             "policia", "bomberos"),
    "Territorio": ("barrio", "localidad"),
    "Cultura y comunidad": ("biblioteca", "teatro", "museo", "centro_comunitario",
                            "club_deportivo", "plaza"),
}
CAPA_DE_TIPO = {t: capa for capa, tipos in CAPAS_MAPA.items() for t in tipos}


def _limite(municipio: str) -> Optional[dict]:
    """El contorno del partido, si ya se bajo de OSM.

    Cambia el encuadre del mapa, y no es cosmetico: encuadrar por los puntos
    hace que un partido censado solo en su casco urbano parezca cubierto entero.
    Con el contorno se ve el area vacia, que es el dato util.
    """
    filas = _filas(
        SQLITE_TERRITORIO,
        "SELECT anillos, lat_min, lat_max, lon_min, lon_max FROM limites "
        "WHERE municipio = ?",
        (municipio,),
    )
    if not filas:
        return None
    import json as _json

    f = filas[0]
    try:
        anillos = _json.loads(f["anillos"])
    except (TypeError, ValueError):
        return None
    return {
        "anillos": anillos,
        "lat_min": f["lat_min"], "lat_max": f["lat_max"],
        "lon_min": f["lon_min"], "lon_max": f["lon_max"],
    }


def territorio(municipio: str) -> dict:
    """Entidades del municipio, listas para dibujar en un mapa.

    Devuelve el contorno del partido si esta bajado, y el recuadro de las
    entidades como respaldo: sin contorno el mapa sigue andando, encuadrado por
    los puntos como antes.
    """
    filas = _filas(
        SQLITE_TERRITORIO,
        "SELECT tipo, nombre, latitud, longitud, direccion, telefono, web, "
        "operador, url_fuente FROM entidades WHERE municipio = ? ORDER BY tipo, nombre",
        (municipio,),
    )
    for f in filas:
        f["capa"] = CAPA_DE_TIPO.get(f["tipo"], "Otros")

    ubicadas = [f for f in filas if f["latitud"] is not None and f["longitud"] is not None]
    recuadro = None
    if ubicadas:
        lats = [f["latitud"] for f in ubicadas]
        lons = [f["longitud"] for f in ubicadas]
        recuadro = {"lat_min": min(lats), "lat_max": max(lats),
                    "lon_min": min(lons), "lon_max": max(lons)}

    conteo: Dict[str, int] = {}
    for f in filas:
        conteo[f["tipo"]] = conteo.get(f["tipo"], 0) + 1

    return {
        "municipio": municipio,
        "total": len(filas),
        "ubicadas": len(ubicadas),
        "recuadro": recuadro,
        "limite": _limite(municipio),
        "por_tipo": conteo,
        "entidades": filas,
    }


NIVELES_EDUCATIVOS = {
    "jardin": "Inicial / Jardín",
    "escuela_primaria": "Primaria",
    "escuela_secundaria": "Secundaria y técnica",
    "escuela_especial": "Especial",
    "educacion_superior": "Superior / Terciaria",
    "escuela_sin_clasificar": "Sin nivel identificado",
}

# Como se lee cada variable de Fase 4 en la ficha resumida.
FILA_VARIABLE = {
    "sistema_rafam": "RAFAM",
    "expediente_digital_gde": "Expediente digital (GDE/GEDO)",
    "app_municipal": "App municipal",
    "tramites_online": "Trámites online",
    "pago_online_tasas": "Cobro de tasas online",
    "reclamos_147": "Reclamos 147",
    "transparencia_presupuesto": "Presupuesto publicado",
    "boletin_oficial": "Boletín oficial",
    "licitaciones": "Licitaciones",
}


def _censo_indec(nombre: str) -> dict:
    """Poblacion oficial y apertura por sexo, si el modulo INDEC ya corrio."""
    filas = _filas(
        SQLITE_INDEC,
        "SELECT poblacion_indec_2022, mujeres, varones, poblacion_gold, fuente "
        "FROM censo_2022 WHERE municipio = ?",
        (nombre,),
    )
    return filas[0] if filas else {}


def _gabinete(nombre: str) -> dict:
    """Intendente y secretarios, con la cita del decreto que los prueba.

    Cuando dos fuentes nombran a personas distintas para el mismo cargo se guardan
    las dos filas (el id incluye la fuente). Aca gana el boletin, que es un
    decreto publicado; el portal queda como corroboracion.
    """
    filas = _filas(
        SQLITE_GABINETE,
        "SELECT cargo, area, nombre, cita, url, confianza, fecha_norma, fuente "
        "FROM autoridades WHERE municipio = ? ORDER BY cargo, area",
        (nombre,),
    )
    peso = {"boletin_oficial": 0, "portal": 1, "red_oficial": 2}
    mejor: dict = {}
    for f in filas:
        clave = (f["cargo"], (f["area"] or "").lower())
        actual = mejor.get(clave)
        if actual is None or peso.get(f["fuente"], 9) < peso.get(actual["fuente"], 9):
            mejor[clave] = f

    intendente = next((f for f in mejor.values() if f["cargo"] == "intendente"), None)
    secretarios = sorted(
        (f for f in mejor.values() if f["cargo"] == "secretario"),
        key=lambda f: f["area"] or "",
    )
    return {"intendente": intendente, "secretarios": secretarios}


def _seguridad(nombre: str) -> dict:
    """Delito denunciado del SNIC, con el puesto y las advertencias.

    El nivel viaja SIEMPRE con su explicacion. "Alto" sin aclarar que es relativo
    a los 86 y que son denuncias se lee como "peligroso", que es afirmar algo que
    el dato no dice.
    """
    filas = _filas(
        SQLITE_SEGURIDAD,
        "SELECT anio, nivel, tasa_indice, hechos_indice, tasa_personas, "
        "tasa_propiedad, tasa_sexual, homicidios, tasa_homicidios, robos, "
        "tasa_robos, tasa_actividad_policial, poblacion_estacional, fuente "
        "FROM seguridad WHERE municipio = ?",
        (nombre,),
    )
    if not filas:
        return {"disponible": False}

    f = dict(filas[0])
    ranking = _filas(
        SQLITE_SEGURIDAD,
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN tasa_indice > (SELECT tasa_indice FROM seguridad "
        "WHERE municipio = ?) THEN 1 ELSE 0 END) AS arriba FROM seguridad",
        (nombre,),
    )
    f["disponible"] = True
    f["total"] = ranking[0]["total"] if ranking else None
    f["puesto"] = (ranking[0]["arriba"] + 1) if ranking else None
    f["advertencias"] = [
        "Son hechos DENUNCIADOS, no delitos ocurridos: donde se denuncia menos, "
        "el número baja sin que baje el delito.",
        "El nivel es RELATIVO a los 86 municipios relevados. «Alto» significa "
        "«en el tercio superior», no «peligroso».",
        "El índice deja afuera estupefacientes y armas: se detectan por acción "
        "policial, no por denuncia de una víctima. Se informan aparte.",
    ]
    if f.get("poblacion_estacional"):
        f["advertencias"].append(
            "Partido BALNEARIO: la tasa está inflada porque los hechos ocurren "
            "sobre la población de verano y se dividen por la residente."
        )
    return f


def _como_opera(nombre: str) -> dict:
    """Que tiene y como opera el municipio, leido de su prensa local.

    Los siete aspectos aparecen SIEMPRE, con evidencia o sin ella: si solo se
    mostraran los verificados, la ficha daria a entender que lo demas no existe.
    Y lo que falta no es "no tiene": es "la prensa leida no lo publico".
    """
    verificados = {
        f["aspecto"]: f
        for f in _filas(
            SQLITE_OPERATIVOS,
            "SELECT aspecto, detalle, cita, medio, url, fecha_nota "
            "FROM operativos WHERE municipio = ?",
            (nombre,),
        )
    }
    resumen = _filas(
        SQLITE_OPERATIVOS,
        "SELECT medios_leidos, notas_del_municipio FROM municipios_operativos "
        "WHERE municipio = ?",
        (nombre,),
    )
    return {
        "disponible": bool(resumen),
        "medios_leidos": resumen[0]["medios_leidos"] if resumen else 0,
        "notas": resumen[0]["notas_del_municipio"] if resumen else 0,
        "aspectos": [
            {"clave": clave, "etiqueta": etiqueta, "evidencia": verificados.get(clave)}
            for clave, etiqueta in ASPECTOS_SEGURIDAD
        ],
        "advertencia": (
            "Ausencia de evidencia no es evidencia de ausencia: que la prensa "
            "leída no lo haya publicado en 12 meses no prueba que el municipio "
            "no lo tenga."
        ),
    }


def ficha_resumida(nombre: str) -> dict:
    """La ficha de un municipio como la leería una persona, no una base.

    Cruza las tres capas: poblacion del Gold Standard, variables de Fase 4 con
    su evidencia, y el censo territorial de Fase 6.

    Todo lo que no se sabe se dice. ADR-0009: un vacio se muestra como vacio,
    con el motivo, y no se rellena.
    """
    base = ficha(nombre)
    if not base:
        return {}
    ent = territorio(nombre)
    hallazgos = {h["variable"]: h for h in base.get("hallazgos", [])}

    def dato(variable: str) -> dict:
        h = hallazgos.get(variable)
        if not h or h["estado"] != "verificado":
            return {"valor": None, "motivo": "No verificable en el portal oficial"}
        return {
            "valor": h["valor"], "detalle": h.get("detalle"),
            "fragmento": h.get("fragmento"), "url": h.get("url"),
            "confianza": h.get("confianza"),
        }

    conteo = ent["por_tipo"]
    educacion = {
        etiqueta: conteo.get(tipo, 0)
        for tipo, etiqueta in NIVELES_EDUCATIVOS.items()
        if conteo.get(tipo, 0)
    }
    hospitales = [e for e in ent["entidades"] if e["tipo"] == "hospital"]
    caps = [e for e in ent["entidades"] if e["tipo"] == "caps"]
    estaciones = [e for e in ent["entidades"] if e["tipo"] == "estacion_tren"]

    canal = hallazgos.get("canal_turnos_salud")
    canal_valor = canal["valor"] if canal and canal["estado"] == "verificado" else None

    # Poblacion: manda INDEC, que tiene norma, ano y metodologia publicada. El
    # Gold Standard se muestra al lado cuando difieren, porque la diferencia es
    # un dato en si misma: hay filas cruzadas entre municipios (handoff §5.1) y
    # verlas es lo que permitio detectarlas.
    censo = _censo_indec(nombre)
    gold = base.get("poblacion")
    indec = censo.get("poblacion_indec_2022")
    # El porcentaje se calcula sobre la suma de mujeres y varones, NO sobre la
    # poblacion total: el total del censo incluye a quienes no declararon sexo,
    # asi que dividir por el total daria dos porcentajes que no suman 100.
    mujeres, varones = censo.get("mujeres"), censo.get("varones")
    con_sexo = (mujeres or 0) + (varones or 0)
    poblacion = {
        "total": indec or gold,
        "fuente": (
            censo.get("fuente") if indec else "Gold Standard (relevamiento manual verificado)"
        ),
        "mujeres": mujeres,
        "varones": varones,
        "pct_mujeres": round(mujeres / con_sexo * 100, 1) if con_sexo else None,
        "pct_varones": round(varones / con_sexo * 100, 1) if con_sexo else None,
        "viviendas": None,
        "falta": (
            None
            if censo.get("mujeres")
            else "Apertura por sexo: el modulo INDEC todavia no corrio para este municipio"
        ),
        "falta_viviendas": (
            "Viviendas por partido: no esta en la serie de poblacion de INDEC, "
            "hay que buscarla en la de hogares"
        ),
        "gold": gold if (indec and gold and indec != gold) else None,
    }

    gab = _gabinete(nombre)

    return {
        "municipio": nombre,
        "id_municipio": base["id_municipio"],
        "poblacion": poblacion,
        "seguridad": _seguridad(nombre),
        "como_opera": _como_opera(nombre),
        "autoridades": {
            # Del Boletin Oficial y del portal (src/gabinete), no de Fase 4: el
            # portal casi nunca nombra al intendente y Fase 4 daba 0 verificados.
            "intendente": gab["intendente"],
            "secretarios": gab["secretarios"],
            # El Concejo sigue viniendo de Fase 4: todavia no tiene modulo propio.
            "concejales": dato("concejales"),
        },
        "educacion": {
            "total": sum(educacion.values()),
            "por_nivel": educacion,
            "fuente": "OpenStreetMap (cobertura parcial, colaborativa)",
        },
        "salud": {
            "hospitales": [
                {"nombre": h["nombre"], "direccion": h["direccion"], "url": h["url_fuente"]}
                for h in hospitales
            ],
            "caps": len(caps),
            "caps_nombrados": [c["nombre"] for c in caps if c["nombre"]],
            "farmacias": conteo.get("farmacia", 0),
            "turnos_canal": canal_valor,
            "turnos_evidencia": canal.get("fragmento") if canal else None,
            "turnos_url": canal.get("url") if canal else None,
        },
        "digital": {etiqueta: dato(v) for v, etiqueta in FILA_VARIABLE.items()},
        "ambiental": _ambiental(nombre),
        "sitio_oficial": base.get("sitio_oficial"),
        "sitio_sin_https": base.get("sitio_sin_https"),
        "transporte": {
            "estaciones_tren": [
                {"nombre": e["nombre"], "url": e["url_fuente"]} for e in estaciones
            ],
            "colectivo": None,
            "falta": "Líneas de colectivo urbano: no relevado todavía",
        },
    }


# ---------------------------------------------------------------------------
# Ambiental
# ---------------------------------------------------------------------------

CATEGORIAS_AMBIENTAL = (
    ("promotores_ambientales", "Promotores ambientales"),
    ("fiscalizacion_3ra", "Fiscalización 3ra categoría"),
    ("girsu_residuos", "GIRSU y residuos"),
    ("areas_arbolado", "Áreas protegidas y arbolado"),
    ("otras_acciones", "Otras acciones ambientales"),
)

# Como se lee cada etiqueta derivada. La etiqueta sola no significa nada para
# quien mira el tablero: "mixta" tiene que decir mixta ENTRE QUIEN Y QUIEN.
GLOSA_AMBIENTAL = {
    "mixta": "Provincia fiscaliza 3ra; el municipio controla 1ra y 2da o inspecciona junto a ella",
    "provincial": "La fiscaliza la Provincia (Ley 11.459); no se describe rol municipal",
    "municipal": "El texto solo describe control municipal",
    "sin_clasificar": "El texto no dice quién ejerce el control",
    "cuerpo_nombrado": "Nombra promotores o promotoras propios",
    "planta_propia": "Tiene planta de tratamiento, separación o reciclado",
    "puntos_verdes": "Tiene puntos verdes o puntos limpios",
    "planta_propia+puntos_verdes": "Tiene planta y además puntos verdes",
    "reserva_declarada": "Tiene reserva o área protegida declarada",
    "plan_arbolado": "Tiene plan u ordenanza de arbolado",
    "reserva_declarada+plan_arbolado": "Tiene reserva declarada y plan de arbolado",
    "ordenanza_fitosanitarios": "Regula fitosanitarios o agroquímicos",
    "sin_senal": "El texto no menciona ninguna de las señales buscadas",
}


def _ambiental(nombre: str) -> dict:
    """El plan ambiental del municipio, tal como lo relevo una persona.

    El texto es lo que manda y viaja siempre entero. El `estado` es una lectura
    DERIVADA con palabras clave, para que los 86 se puedan comparar: un parrafo
    en prosa no permite ordenar ni filtrar. Por eso se muestran juntos, y por eso
    cada etiqueta viene con su glosa.
    """
    filas = _filas(
        SQLITE_TEMAS,
        "SELECT categoria, texto, estado, fuentes, seccion, poblacion, origen "
        "FROM plan_ambiental WHERE municipio = ?",
        (nombre,),
    )
    if not filas:
        return {"hay_datos": False, "motivo": "Sin relevamiento ambiental cargado"}

    por_id = {f["categoria"]: f for f in filas}
    return {
        "hay_datos": True,
        "origen": filas[0]["origen"],
        "seccion": filas[0]["seccion"],
        "fuentes": [u.strip() for u in (filas[0]["fuentes"] or "").split(";") if u.strip()],
        "categorias": [
            {
                "id": cid,
                "etiqueta": etiqueta,
                "texto": por_id[cid]["texto"],
                "estado": por_id[cid]["estado"],
                "glosa": GLOSA_AMBIENTAL.get(por_id[cid]["estado"], ""),
            }
            for cid, etiqueta in CATEGORIAS_AMBIENTAL
            if cid in por_id
        ],
    }


def ambiental() -> dict:
    """Los 86 comparados por categoria, para la vista de conjunto."""
    filas = _filas(
        SQLITE_TEMAS,
        "SELECT municipio, seccion, poblacion, categoria, estado, texto, fuentes "
        "FROM plan_ambiental",
    )
    if not filas:
        return {"hay_datos": False, "municipios": [], "por_categoria": []}

    municipios: Dict[str, dict] = {}
    for f in filas:
        m = municipios.setdefault(
            f["municipio"],
            {"municipio": f["municipio"], "seccion": f["seccion"],
             "poblacion": f["poblacion"], "fuentes": f["fuentes"],
             "estados": {}, "textos": {}},
        )
        m["estados"][f["categoria"]] = f["estado"]
        m["textos"][f["categoria"]] = f["texto"]

    por_categoria = []
    for cid, etiqueta in CATEGORIAS_AMBIENTAL:
        conteo: Dict[str, int] = {}
        for m in municipios.values():
            e = m["estados"].get(cid)
            if e:
                conteo[e] = conteo.get(e, 0) + 1
        por_categoria.append({
            "id": cid,
            "etiqueta": etiqueta,
            "estados": [
                {"estado": e, "n": n, "glosa": GLOSA_AMBIENTAL.get(e, "")}
                for e, n in sorted(conteo.items(), key=lambda x: -x[1])
            ],
        })

    return {
        "hay_datos": True,
        "total": len(municipios),
        "categorias": [{"id": c, "etiqueta": e} for c, e in CATEGORIAS_AMBIENTAL],
        "por_categoria": por_categoria,
        "municipios": sorted(municipios.values(), key=lambda m: m["municipio"]),
    }


def resumen_territorio() -> dict:
    """Cobertura del censo territorial sobre los 86."""
    filas = _filas(
        SQLITE_TERRITORIO,
        "SELECT municipio, total_entidades, ubicadas FROM municipios_territorio",
    )
    por_tipo = _filas(
        SQLITE_TERRITORIO, "SELECT tipo, COUNT(*) n FROM entidades GROUP BY tipo ORDER BY n DESC"
    )
    return {
        "municipios_censados": len(filas),
        "entidades": sum(f["total_entidades"] for f in filas),
        "por_tipo": {f["tipo"]: f["n"] for f in por_tipo},
        "por_capa": {
            capa: sum(f["n"] for f in por_tipo if CAPA_DE_TIPO.get(f["tipo"]) == capa)
            for capa in CAPAS_MAPA
        },
        "municipios": sorted(filas, key=lambda f: -f["total_entidades"]),
    }


def parametros_impacto() -> List[dict]:
    """Los parametros del modelo de impacto, con su procedencia."""
    from parametros import CATALOGO

    return [
        {
            "nombre": p.nombre,
            "valor": p.valor,
            "unidad": p.unidad,
            "tipo": p.tipo.value,
            "afirmable": p.es_afirmable,
            "fuente": p.citar(),
            "nota": p.nota,
            "minimo": p.minimo,
            "maximo": p.maximo,
        }
        for p in CATALOGO.values()
    ]


def costo_turnos() -> dict:
    """Costo social de no tener turnos digitales, con sus advertencias."""
    from modelo_turnos import advertencias, sensibilidad, techo_de_precio_anual
    from motor_impacto import municipios_sin_canal_digital

    try:
        costos = municipios_sin_canal_digital(SQLITE_HALLAZGOS)
    except FileNotFoundError:
        return {"disponible": False, "municipios": [], "advertencias": [], "sensibilidad": []}

    filas = []
    for c in costos:
        t_min, _, t_max = techo_de_precio_anual(c)
        filas.append(
            {
                "municipio": c.municipio,
                "poblacion": c.poblacion,
                "canal_actual": c.canal_actual,
                "costo_min": round(c.costo_min),
                "costo_max": round(c.costo_max),
                "techo_mensual_min": round(t_min / 12),
                "techo_mensual_max": round(t_max / 12),
                "evidencia": c.evidencia,
                "url": c.url,
            }
        )
    return {
        "disponible": True,
        "municipios": filas,
        "total_min": sum(f["costo_min"] for f in filas),
        "total_max": sum(f["costo_max"] for f in filas),
        "advertencias": advertencias(),
        "sensibilidad": [
            {"parametro": n, "factor": round(f, 1), "como_cerrarlo": c}
            for n, f, c in sensibilidad()
        ],
    }


# ---------------------------------------------------------------------------
# Comercial (src/oportunidades)
# ---------------------------------------------------------------------------

# Mismo peso que en comercial.py. Se repite a proposito en vez de importarlo:
# el tablero no debe arrastrar el paquete de oportunidades solo para mostrar
# numeros, y si el peso cambia alla, aca se ve como una discrepancia y no como
# un cambio silencioso.
_PESO = {"alta": 5, "media": 2, "baja": 1}


def comercial() -> dict:
    """Que le puede vender UDS a cada municipio, con la cita que lo prueba.

    Es la unica vista del tablero que muestra INTERPRETACION y no solo evidencia.
    Por eso cada fila viaja siempre con su cita y su URL: el que la lee tiene que
    poder desconfiar del texto y verificar la fuente en un clic.
    """
    filas = _filas(
        SQLITE_OPORTUNIDADES,
        "SELECT municipio, area, producto, problema, friccion, cita, url "
        "FROM oportunidades",
    )
    if not filas:
        return {"disponible": False, "municipios": [], "productos": [], "total": 0}

    por_municipio: dict = {}
    for f in filas:
        m = por_municipio.setdefault(
            f["municipio"], {"municipio": f["municipio"], "oportunidades": [], "puntaje": 0}
        )
        m["oportunidades"].append(f)
        m["puntaje"] += _PESO.get(f["friccion"], 1)

    orden = {"alta": 0, "media": 1, "baja": 2}
    for m in por_municipio.values():
        m["oportunidades"].sort(key=lambda o: orden.get(o["friccion"], 9))

    productos: dict = {}
    for f in filas:
        p = productos.setdefault(
            f["producto"], {"producto": f["producto"], "area": f["area"], "municipios": 0}
        )
        p["municipios"] += 1

    return {
        "disponible": True,
        "total": len(filas),
        "municipios": sorted(
            por_municipio.values(),
            key=lambda m: (-m["puntaje"], -len(m["oportunidades"]), m["municipio"]),
        ),
        "productos": sorted(productos.values(), key=lambda p: -p["municipios"]),
    }


__all__ = [
    "CAPAS_MAPA",
    "cola_de_revision",
    "comercial",
    "ficha_resumida",
    "costo_turnos",
    "ficha",
    "mapa_turnos",
    "municipios",
    "parametros_impacto",
    "resumen",
    "resumen_territorio",
    "territorio",
]
