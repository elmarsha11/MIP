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


def territorio(municipio: str) -> dict:
    """Entidades del municipio, listas para dibujar en un mapa.

    Devuelve tambien el recuadro que las contiene: es lo que permite hacer zoom
    al municipio sin depender de un servicio de mapas externo.
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
        "por_tipo": conteo,
        "entidades": filas,
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


__all__ = [
    "CAPAS_MAPA",
    "cola_de_revision",
    "costo_turnos",
    "ficha",
    "mapa_turnos",
    "municipios",
    "parametros_impacto",
    "resumen",
    "resumen_territorio",
    "territorio",
]
