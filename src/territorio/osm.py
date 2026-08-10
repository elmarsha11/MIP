"""
Fase 6 - OpenStreetMap como fuente de entidades.

OSM tiene, para los municipios bonaerenses, lo que ningun portal municipal
publica: hospitales, CAPS, escuelas, barrios y plazas, con nombre, direccion y
coordenadas. Datos abiertos (ODbL), sin clave y gratis.

Medido el 2026-08-09 en Chascomus: 470 entidades, incluidos el Hospital
Municipal San Vicente de Paul y los CAPS IPORA, El Porteno y San Cayetano.
Contra el relevamiento manual de Juli (1 hospital + 7 CAPS), OSM tiene 5 de 7.
Es incompleto y es honesto decirlo: OSM es colaborativo y su cobertura varia.

Buena vecindad con el servicio publico de Overpass, que es gratuito y tiene 2
slots:
  - una consulta por vez, con espera minima entre consultas
  - todo se cachea en disco: un municipio ya censado no se vuelve a pedir
  - User-Agent identificable
  - si responde algo que no es JSON (limite alcanzado), se espera y se reintenta
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests

try:
    from .entidades import REQUIEREN_NOMBRE, Entidad, FuenteEntidad, TipoEntidad
except ImportError:  # ejecutado como script
    from entidades import (  # type: ignore[no-redef]
        REQUIEREN_NOMBRE,
        Entidad,
        FuenteEntidad,
        TipoEntidad,
    )

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "territorio" / "cache"

# Cadena de servidores Overpass. El publico principal se satura seguido y
# rechaza el primer intento; rotar a un espejo sale mas barato que esperar.
# Mismo criterio que la cadena de modelos de Gemini en Fase 4.
# OJO: solo espejos con cobertura MUNDIAL. overpass.osm.ch es suizo: responde
# 200 con JSON valido y CERO elementos para Argentina. Al tomarlo como respuesta
# autoritativa, el censo concluyo "sin limite administrativo" en 83 de 86
# municipios. Un espejo regional no es una alternativa, es una fuente distinta.
#
# Como se valida un espejo antes de agregarlo (probado el 2026-08-10):
# NO alcanza con preguntarle por nombre. La primera prueba fue pedir
# name="Partido de Chascomús" y los tres candidatos devolvieron cero — pero el
# test estaba mal, porque OSM la llama "Chascomús" a secas. Hay que pedir la
# relacion POR ID, que es inequivoco, y despues correrle la consulta pesada:
#
#     relation(5816495);out tags;      -> tiene que devolver name="Chascomús"
#     CONSULTA_ENTIDADES sobre esa area -> tiene que devolver cientos de
#                                          elementos con latitud cerca de -35,6
#
# Asi se descarto overpass.private.coffee (cero elementos incluso por ID) y se
# acepto maps.mail.ru (335 elementos en 4 segundos, latitudes correctas).
SERVIDORES = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
USER_AGENT = "MIP-relevamiento-municipal/0.1 (uso interno, contacto: UDS)"
INTERVALO_MINIMO = 6.0  # segundos entre consultas: el servicio es gratuito
TIMEOUT = 240
MAX_REINTENTOS = 3
ESPERA_TRAS_LIMITE = 45

_lock = threading.Lock()
_ultima_consulta = 0.0
_servidor_vivo: Optional[str] = None


class OverpassCaido(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Traduccion de etiquetas OSM al vocabulario de MIP
# ---------------------------------------------------------------------------

# Se evalua en orden: la primera regla que matchea gana.
REGLAS: tuple = (
    # (clave_osm, valor_osm, tipo MIP)
    ("amenity", "townhall", TipoEntidad.MUNICIPALIDAD),
    ("amenity", "police", TipoEntidad.POLICIA),
    ("amenity", "fire_station", TipoEntidad.BOMBEROS),
    ("amenity", "pharmacy", TipoEntidad.FARMACIA),
    ("amenity", "library", TipoEntidad.BIBLIOTECA),
    ("amenity", "theatre", TipoEntidad.TEATRO),
    ("amenity", "community_centre", TipoEntidad.CENTRO_COMUNITARIO),
    ("amenity", "social_facility", TipoEntidad.CENTRO_COMUNITARIO),
    ("amenity", "kindergarten", TipoEntidad.JARDIN),
    ("amenity", "college", TipoEntidad.EDUCACION_SUPERIOR),
    ("amenity", "university", TipoEntidad.EDUCACION_SUPERIOR),
    ("tourism", "museum", TipoEntidad.MUSEO),
    ("leisure", "sports_centre", TipoEntidad.CLUB_DEPORTIVO),
    ("leisure", "stadium", TipoEntidad.CLUB_DEPORTIVO),
    ("leisure", "park", TipoEntidad.PLAZA),
    ("place", "neighbourhood", TipoEntidad.BARRIO),
    ("place", "suburb", TipoEntidad.BARRIO),
    ("place", "quarter", TipoEntidad.BARRIO),
    ("place", "town", TipoEntidad.LOCALIDAD),
    ("place", "village", TipoEntidad.LOCALIDAD),
    ("place", "hamlet", TipoEntidad.LOCALIDAD),
    ("railway", "station", TipoEntidad.ESTACION_TREN),
    ("railway", "halt", TipoEntidad.ESTACION_TREN),
)

# Palabras del nombre que definen el tipo cuando la etiqueta OSM es ambigua.
# amenity=hospital cubre desde un hospital de 200 camas hasta una salita, y
# amenity=school no distingue jardin de secundaria. El nombre si.
PISTAS_NOMBRE = (
    ("caps", TipoEntidad.CAPS),
    ("centro de atencion primaria", TipoEntidad.CAPS),
    ("centro atencion primaria", TipoEntidad.CAPS),
    ("sala de primeros auxilios", TipoEntidad.CAPS),
    ("unidad sanitaria", TipoEntidad.CAPS),
    ("salita", TipoEntidad.CAPS),
    ("posta sanitaria", TipoEntidad.CAPS),
    ("hospital", TipoEntidad.HOSPITAL),
    ("clinica", TipoEntidad.CLINICA_PRIVADA),
    ("sanatorio", TipoEntidad.CLINICA_PRIVADA),
    ("jardin", TipoEntidad.JARDIN),
    ("preescolar", TipoEntidad.JARDIN),
    ("primaria", TipoEntidad.ESCUELA_PRIMARIA),
    ("secundaria", TipoEntidad.ESCUELA_SECUNDARIA),
    ("tecnica", TipoEntidad.ESCUELA_SECUNDARIA),
    ("agraria", TipoEntidad.ESCUELA_SECUNDARIA),
    ("especial", TipoEntidad.ESCUELA_ESPECIAL),
    ("instituto superior", TipoEntidad.EDUCACION_SUPERIOR),
    ("terciario", TipoEntidad.EDUCACION_SUPERIOR),
    ("universidad", TipoEntidad.EDUCACION_SUPERIOR),
    ("concejo deliberante", TipoEntidad.CONCEJO_DELIBERANTE),
    ("delegacion", TipoEntidad.DELEGACION),
    ("biblioteca", TipoEntidad.BIBLIOTECA),
    ("bomberos", TipoEntidad.BOMBEROS),
    ("club", TipoEntidad.CLUB_DEPORTIVO),
    ("sociedad de fomento", TipoEntidad.CENTRO_COMUNITARIO),
)


def _normalizar(texto: str) -> str:
    import re
    import unicodedata

    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


def clasificar(etiquetas: dict) -> TipoEntidad:
    """Etiquetas de OSM -> tipo del vocabulario de MIP.

    El nombre manda sobre la etiqueta en salud y educacion: OSM marca como
    'hospital' tanto al Hospital San Vicente de Paul como al CAPS El Porteno, y
    para MIP esa diferencia es justamente el dato.
    """
    nombre = _normalizar(etiquetas.get("name", ""))
    amenity = etiquetas.get("amenity")

    # Las farmacias llevan healthcare=pharmacy. Sin esta salida temprana caian
    # en la heuristica de salud y, al no matchear ninguna pista de nombre
    # ("Bellingeri", "Aprile"), terminaban clasificadas como CAPS: 13 farmacias
    # contadas como centros de salud en Chascomus.
    if amenity == "pharmacy" or etiquetas.get("healthcare") == "pharmacy":
        return TipoEntidad.FARMACIA

    es_salud = amenity in ("hospital", "clinic", "doctors") or "healthcare" in etiquetas
    es_educacion = amenity in ("school", "kindergarten", "college", "university")

    if es_salud or es_educacion:
        for pista, tipo in PISTAS_NOMBRE:
            if pista in nombre:
                return tipo
        if es_salud:
            if amenity == "clinic" or etiquetas.get("healthcare") == "clinic":
                return TipoEntidad.CLINICA_PRIVADA
            if amenity == "hospital":
                return TipoEntidad.HOSPITAL
            return TipoEntidad.CAPS
        return TipoEntidad.ESCUELA_SIN_CLASIFICAR

    for pista, tipo in PISTAS_NOMBRE:
        if pista in nombre and tipo in (
            TipoEntidad.CONCEJO_DELIBERANTE, TipoEntidad.DELEGACION,
            TipoEntidad.BIBLIOTECA, TipoEntidad.BOMBEROS,
            TipoEntidad.CENTRO_COMUNITARIO,
        ):
            return tipo

    for clave, valor, tipo in REGLAS:
        if etiquetas.get(clave) == valor:
            return tipo
    return TipoEntidad.OTRO


# ---------------------------------------------------------------------------
# Cliente Overpass
# ---------------------------------------------------------------------------


def _esperar_turno() -> None:
    global _ultima_consulta
    with _lock:
        falta = INTERVALO_MINIMO - (time.time() - _ultima_consulta)
        if falta > 0:
            time.sleep(falta)
        _ultima_consulta = time.time()


def consultar(query: str, exigir_elementos: bool = False) -> Optional[dict]:
    """Ejecuta una consulta Overpass rotando entre servidores.

    None si ninguno responde. El llamador lo traduce a "sin datos", nunca a un
    dato inventado.
    """
    global _servidor_vivo
    for vuelta in range(1, MAX_REINTENTOS + 1):
        # El que ya funciono se prueba primero: evita reintentar contra el
        # servidor saturado en cada municipio.
        orden = ([_servidor_vivo] if _servidor_vivo else []) + [
            s for s in SERVIDORES if s != _servidor_vivo
        ]
        for servidor in orden:
            _esperar_turno()
            try:
                resp = requests.post(
                    servidor, data={"data": query}, timeout=TIMEOUT,
                    headers={"User-Agent": USER_AGENT},
                )
                if "json" in (resp.headers.get("content-type") or ""):
                    datos = resp.json()
                    # Un espejo con cobertura parcial devuelve 200 y una lista
                    # vacia. Para las consultas donde el vacio seria sospechoso
                    # se prueba otro servidor antes de darlo por bueno.
                    if exigir_elementos and not datos.get("elements"):
                        print(f"    [OSM] {servidor.split('/')[2]} sin resultados, probando otro")
                        continue
                    _servidor_vivo = servidor
                    return datos
                # Overpass devuelve HTML cuando esta saturado o limitando.
                print(f"    [OSM] {servidor.split('/')[2]} saturado, probando otro")
            except requests.RequestException as exc:
                print(f"    [OSM] {servidor.split('/')[2]}: {type(exc).__name__}")
        if vuelta < MAX_REINTENTOS:
            print(f"    [OSM] todos ocupados, esperando {ESPERA_TRAS_LIMITE}s")
            time.sleep(ESPERA_TRAS_LIMITE)
    return None


def _cache(nombre: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / nombre


def resolver_limite(municipio: str) -> Optional[int]:
    """ID de la relacion OSM del PARTIDO. Se cachea: no cambia.

    Los partidos bonaerenses estan en **admin_level=5**, no en 8. Medido el
    2026-08-10 contra OSM: dentro de la provincia hay 135 relaciones de nivel 5
    —exactamente la cantidad de partidos— y 563 de nivel 8, que son las
    LOCALIDADES de adentro.

    Pedir nivel 8 tuvo dos consecuencias, y la segunda es peor que la primera:

      1. Los partidos cuya ciudad cabecera se llama distinto no aparecian. El
         partido de Balcarce es 'Partido de Balcarce' (nivel 5) y su ciudad es
         'San Jose de Balcarce' (nivel 8): no matcheaba por nombre y el
         municipio quedaba sin censar. Fueron ~40 de 86.
      2. Los que SI matcheaban devolvian el casco urbano en vez del partido.
         Chascomus daba 201 entidades de la ciudad y da 235 del partido, con
         las 7 localidades de adentro.

    Lo que este arreglo NO explica: OSM sigue encontrando 5 de los 7 CAPS de
    Chascomus. Se probo la hipotesis de que los 2 faltantes estuvieran fuera del
    casco urbano y es falsa —a nivel partido siguen siendo 5— asi que es
    incompletitud de OSM, que es colaborativo. Se declara y no se rellena.

    El nombre en nivel 5 es siempre 'Partido de X', pero se prueba tambien el
    nombre pelado por si algun partido esta cargado distinto.
    """
    path = _cache("limites.json")
    mapa: Dict[str, Optional[int]] = {}
    if path.exists():
        try:
            mapa = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            mapa = {}
    if municipio in mapa:
        return mapa[municipio]

    nombres = [f"Partido de {municipio}", municipio]
    filtro = "|".join(n.replace('"', "") for n in nombres)
    # La consulta se ACOTA a la provincia de Buenos Aires. Sin eso busca en todo
    # el mundo y hay homonimos: Ayacucho resolvia a relation/1930922, que es
    # Ayacucho de PERU, y despues el validador descartaba todas sus entidades por
    # "latitud fuera de Argentina" dejando al municipio con cero. Lo mismo
    # acecha con Rivadavia, Maipu, 25 de Mayo, San Antonio, Colon y Rojas.
    # ISO3166-2=AR-B identifica a la provincia sin ambiguedad; el nombre solo no,
    # porque "Buenos Aires" tambien es la ciudad.
    datos = consultar(
        f'[out:json][timeout:90];'
        f'area["boundary"="administrative"]["admin_level"="4"]'
        f'["ISO3166-2"="AR-B"]->.prov;'
        f'relation["boundary"="administrative"]["admin_level"="5"]'
        f'["name"~"^({filtro})$",i](area.prov);out ids tags;',
        exigir_elementos=True,  # 0 resultados puede ser un espejo incompleto
    )
    encontrado = None
    if datos:
        elementos = datos.get("elements", [])
        # Si hay varios, gana el que se llama "Partido de X": es el nombre
        # canonico del nivel 5.
        partidos = [e for e in elementos if str(e["tags"].get("name", "")).lower().startswith("partido")]
        elegido = (partidos or elementos or [None])[0]
        if elegido:
            encontrado = elegido["id"]

    if encontrado is not None:
        # Solo se cachea el acierto. Un None puede ser "OSM no lo tiene" o
        # "Overpass estaba saturado en esta corrida"; guardarlo congelaria el
        # error para siempre y el municipio quedaria sin censar sin motivo real.
        # Mismo criterio que las pistas de Wikidata en Fase 3.
        mapa[municipio] = encontrado
        try:
            path.write_text(json.dumps(mapa, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    return encontrado


CONSULTA_ENTIDADES = """
[out:json][timeout:180];
area({area})->.a;
(
  nwr["amenity"~"^(hospital|clinic|doctors|pharmacy|school|kindergarten|college|university|townhall|police|fire_station|library|theatre|community_centre|social_facility)$"](area.a);
  nwr["healthcare"](area.a);
  nwr["tourism"="museum"](area.a);
  nwr["leisure"~"^(sports_centre|stadium|park)$"](area.a);
  nwr["place"~"^(neighbourhood|suburb|quarter|town|village|hamlet)$"](area.a);
  nwr["railway"~"^(station|halt)$"](area.a);
  nwr["public_transport"="station"](area.a);
);
out center tags;
"""


def censar(municipio: str, id_municipio: str, fecha: str, refrescar: bool = False) -> List[Entidad]:
    """Todas las entidades del municipio segun OSM."""
    # El limite se resuelve SIEMPRE primero, aunque haya cache: la clave del
    # cache incluye la relacion OSM.
    #
    # Antes se llamaba osm_MUN-BA-049.json a secas, y eso dejo a Ayacucho
    # roto de una forma invisible: la respuesta cacheada tenia 731 entidades
    # de Ayacucho de PERU (latitudes -13), de cuando la consulta de limites
    # buscaba en todo el mundo. Se corrigio la consulta, el limite paso a ser
    # el correcto... y el cache siguio devolviendo Peru, porque su nombre no
    # dependia de la relacion. El municipio quedaba en cero sin error visible.
    osm_id = resolver_limite(municipio)
    if osm_id is None:
        print(f"    [OSM] sin limite administrativo para {municipio}")
        return []

    path = _cache(f"osm_{id_municipio}_r{osm_id}.json")
    crudo = None
    if path.exists() and not refrescar:
        try:
            crudo = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            crudo = None

    if crudo is None:
        crudo = consultar(
            CONSULTA_ENTIDADES.format(area=3600000000 + osm_id),
            # Un partido bonaerense sin UNA sola escuela, plaza o barrio en OSM
            # no existe: si vuelve vacio es un espejo con cobertura parcial, no
            # un municipio sin nada. Es la trampa documentada en el handoff.
            exigir_elementos=True,
        )
        if crudo is None:
            raise OverpassCaido(f"Overpass no respondio para {municipio}")
        # Solo se cachea el acierto: una respuesta vacia congelaria el fallo.
        if crudo.get("elements"):
            try:
                path.write_text(json.dumps(crudo, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass

    entidades: List[Entidad] = []
    for elemento in crudo.get("elements", []):
        etiquetas = elemento.get("tags") or {}
        if not etiquetas:
            continue
        tipo = clasificar(etiquetas)
        if tipo in REQUIEREN_NOMBRE and not etiquetas.get("name"):
            continue  # poligono importado sin nombre: no es una entidad censable

        centro = elemento.get("center") or {}
        lat = elemento.get("lat", centro.get("lat"))
        lon = elemento.get("lon", centro.get("lon"))
        referencia = f"{elemento['type']}/{elemento['id']}"
        direccion = " ".join(
            filter(None, [etiquetas.get("addr:street"), etiquetas.get("addr:housenumber")])
        ) or None

        try:
            entidades.append(
                Entidad(
                    municipio=municipio,
                    id_municipio=id_municipio,
                    tipo=tipo,
                    nombre=etiquetas.get("name"),
                    latitud=lat,
                    longitud=lon,
                    direccion=direccion,
                    telefono=etiquetas.get("phone") or etiquetas.get("contact:phone"),
                    web=etiquetas.get("website") or etiquetas.get("contact:website"),
                    operador=etiquetas.get("operator"),
                    fuente=FuenteEntidad.OSM,
                    id_en_fuente=referencia,
                    url_fuente=f"https://www.openstreetmap.org/{referencia}",
                    fecha=fecha,
                    etiquetas_crudas=etiquetas,
                )
            )
        except ValueError as exc:
            # Coordenada imposible u otra inconsistencia: se descarta y se avisa.
            print(f"    [OSM] {referencia} descartada: {str(exc)[:80]}")
    return entidades


__all__ = ["SERVIDORES", "OverpassCaido", "censar", "clasificar", "consultar", "resolver_limite"]
