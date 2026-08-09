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

OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "MIP-relevamiento-municipal/0.1 (uso interno, contacto: UDS)"
INTERVALO_MINIMO = 6.0  # segundos entre consultas: el servicio es gratuito
TIMEOUT = 240
MAX_REINTENTOS = 3
ESPERA_TRAS_LIMITE = 45

_lock = threading.Lock()
_ultima_consulta = 0.0


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


def consultar(query: str) -> Optional[dict]:
    """Ejecuta una consulta Overpass. None si el servicio no responde."""
    for intento in range(1, MAX_REINTENTOS + 1):
        _esperar_turno()
        try:
            resp = requests.post(
                OVERPASS, data={"data": query}, timeout=TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            )
            if "json" in (resp.headers.get("content-type") or ""):
                return resp.json()
            # Overpass devuelve HTML cuando esta saturado o limitando.
            print(f"    [OSM] respuesta no-JSON (intento {intento}), esperando...")
        except requests.RequestException as exc:
            print(f"    [OSM] {type(exc).__name__} (intento {intento})")
        if intento < MAX_REINTENTOS:
            time.sleep(ESPERA_TRAS_LIMITE)
    return None


def _cache(nombre: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / nombre


def resolver_limite(municipio: str) -> Optional[int]:
    """ID de la relacion OSM del partido. Se cachea: no cambia.

    Los partidos bonaerenses estan en admin_level=8. Algunos figuran como
    'Chascomus' y otros como 'Partido de Adolfo Alsina', asi que se prueban las
    dos formas.
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

    nombres = [municipio, f"Partido de {municipio}"]
    filtro = "|".join(n.replace('"', "") for n in nombres)
    datos = consultar(
        f'[out:json][timeout:90];'
        f'relation["boundary"="administrative"]["admin_level"="8"]'
        f'["name"~"^({filtro})$",i];out ids tags;'
    )
    encontrado = None
    if datos:
        elementos = datos.get("elements", [])
        # Si hay varios, gana el que se llama "Partido de X": es el partido
        # entero y no solo la ciudad cabecera.
        partidos = [e for e in elementos if str(e["tags"].get("name", "")).lower().startswith("partido")]
        elegido = (partidos or elementos or [None])[0]
        if elegido:
            encontrado = elegido["id"]

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
);
out center tags;
"""


def censar(municipio: str, id_municipio: str, fecha: str, refrescar: bool = False) -> List[Entidad]:
    """Todas las entidades del municipio segun OSM."""
    path = _cache(f"osm_{id_municipio}.json")
    crudo = None
    if path.exists() and not refrescar:
        try:
            crudo = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            crudo = None

    if crudo is None:
        osm_id = resolver_limite(municipio)
        if osm_id is None:
            print(f"    [OSM] sin limite administrativo para {municipio}")
            return []
        crudo = consultar(CONSULTA_ENTIDADES.format(area=3600000000 + osm_id))
        if crudo is None:
            raise OverpassCaido(f"Overpass no respondio para {municipio}")
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


__all__ = ["OverpassCaido", "censar", "clasificar", "consultar", "resolver_limite"]
