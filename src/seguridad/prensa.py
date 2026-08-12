"""
Lectura de los medios locales: notas de seguridad de los ultimos 12 meses.

Medido el 2026-08-12 sobre los 116 medios alternativos con URL:

  - **25 de 45 exponen la API REST de WordPress.** Da fecha, busqueda del lado
    del servidor y paginacion: es la via barata y la unica que permite pedir
    "todo lo que diga allanamiento desde hace un anio" sin bajar el sitio entero.
  - 30 de 40 exponen RSS o sitemap, pero el RSS trae las ultimas ~15 notas: no
    sirve para 12 meses. El sitemap si, y queda como respaldo.

**Por que se busca dirigido y no se lee todo.** Solo "policia" da 5.954 notas en
12 meses en 25 medios. Leerlas todas seria carisimo y, peor, volveria a medir
COBERTURA DE PRENSA: un partido con tres diarios tendria mas "seguridad" que uno
con una pagina de Facebook. Cuanto delito hay lo responde el SNIC. Lo que se le
pide a la prensa es otra cosa: que fuerzas actuan, que infraestructura tiene el
municipio y como interviene. Eso son hechos concretos que se buscan por nombre.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional
from urllib.parse import urljoin

import requests

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
if str(PROJECT_ROOT / "src" / "discovery") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src" / "discovery"))

CABECERAS = {"User-Agent": "MIP-relevamiento-municipal/0.1 (uso interno, contacto: UDS)"}
TIMEOUT = 25
MESES = 12
MAX_POR_CONSULTA = 20

# Lo que se le pregunta a la prensa. Cada entrada es un aspecto del eje "como
# operan", con los terminos que lo nombran en una nota. No son categorias de
# delito —eso es del SNIC— sino de RESPUESTA del municipio y de las fuerzas.
CONSULTAS: Dict[str, tuple] = {
    "patrulla_urbana": ("patrulla urbana", "patrulla municipal", "policia local"),
    "centro_monitoreo": ("centro de monitoreo", "camaras de seguridad", "videovigilancia"),
    "policia_bonaerense": ("policia bonaerense", "comisaria", "destacamento"),
    "fuerzas_federales": ("gendarmeria", "policia federal", "prefectura"),
    "allanamientos": ("allanamiento", "allanamientos"),
    "operativos": ("operativo de control", "operativo de saturacion", "megaoperativo"),
    "alarmas_vecinales": ("alarmas comunitarias", "boton antipanico", "alarmas vecinales"),
}


class Nota(NamedTuple):
    medio: str
    url_medio: str
    aspecto: str
    termino: str
    titulo: str
    fecha: str
    url: str
    texto: str


def _desde() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=30 * MESES)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


def _sin_html(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", texto or "")).strip()


def api_wordpress(base: str, sesion=None) -> Optional[str]:
    """La URL de la API si el medio la expone, o None.

    Se prueba con una consulta real y no pidiendo el indice: hay sitios que
    responden /wp-json pero tienen los posts cerrados.
    """
    ses = sesion or requests
    api = urljoin(base, "wp-json/wp/v2/posts")
    try:
        r = ses.get(api, params={"per_page": 1, "_fields": "id"}, headers=CABECERAS, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if r.status_code >= 400 or "json" not in (r.headers.get("content-type") or ""):
        return None
    try:
        return api if isinstance(r.json(), list) else None
    except ValueError:
        return None


def buscar(
    medio: str, base: str, api: str, aspecto: str, termino: str, sesion=None
) -> List[Nota]:
    """Notas de ese medio que mencionan el termino, en la ventana de 12 meses."""
    ses = sesion or requests
    try:
        r = ses.get(
            api,
            params={
                "search": termino,
                "after": _desde(),
                "per_page": MAX_POR_CONSULTA,
                "orderby": "date",
                "order": "desc",
                "_fields": "date,link,title,excerpt,content",
            },
            headers=CABECERAS,
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return []
    if r.status_code >= 400:
        return []
    try:
        datos = r.json()
    except ValueError:
        return []
    if not isinstance(datos, list):
        return []

    salida = []
    for d in datos:
        titulo = _sin_html((d.get("title") or {}).get("rendered", ""))
        cuerpo = _sin_html((d.get("content") or {}).get("rendered", "")) or _sin_html(
            (d.get("excerpt") or {}).get("rendered", "")
        )
        if not titulo or not cuerpo:
            continue
        salida.append(
            Nota(
                medio=medio,
                url_medio=base,
                aspecto=aspecto,
                termino=termino,
                titulo=titulo,
                fecha=(d.get("date") or "")[:10],
                url=d.get("link") or base,
                # Se recorta: una nota entera es mucho contexto para lo que se
                # le pregunta, y el dato vive en los primeros parrafos.
                texto=cuerpo[:2500],
            )
        )
    return salida


def _sin_tildes(texto: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# Lugares que un medio local republica constantemente. Si la nota los nombra en
# el TITULO y no nombra al municipio propio, es noticia de afuera.
AJENAS = (
    # Grandes centros bonaerenses y del pais
    "mar del plata", "la plata", "buenos aires", "caba", "rosario", "cordoba",
    "bahia blanca", "quilmes", "lomas de zamora", "la matanza", "avellaneda",
    "san isidro", "tigre", "moron", "lanus", "berazategui", "pilar", "escobar",
    "zarate", "campana", "lujan", "mercedes", "junin", "pergamino", "tandil",
    "olavarria", "azul", "necochea", "san nicolas", "san pedro", "la costa",
    "santa fe", "mendoza", "tucuman", "salta", "neuquen", "chubut", "misiones",
    # Internacional: los medios chicos levantan cable internacional
    "brasil", "chile", "uruguay", "paraguay", "bolivia", "estados unidos",
    "rio de janeiro", "sao paulo", "santiago", "montevideo", "espana", "mexico",
)


def _otros_municipios(municipio: str) -> tuple:
    """Los otros 85 del relevamiento, para no heredarles las noticias.

    Se agrego despues de ver que un medio de Baradero titulaba "CRIMEN DEL
    JUBILADO EN ZARATE" y la nota pasaba el filtro: AJENAS solo tenia las
    ciudades grandes, asi que cualquier otro partido se colaba. La lista de los
    86 ya existe, usarla es gratis y cierra el agujero de raiz.
    """
    from discovery_engine import cargar_municipios

    propio = _sin_tildes(municipio)
    salida = []
    for m in cargar_municipios():
        otro = _sin_tildes(m.nombre)
        if otro == propio:
            continue
        # Solo las partes largas: "General" no distingue a nadie y descartaria
        # las notas de los doce partidos que empiezan asi.
        salida += [
            p for p in otro.split()
            if len(p) > 5 and p not in ("general", "coronel", "capitan", "adolfo")
        ]
    return tuple(sorted(set(salida)))


_CACHE_OTROS: Dict[str, tuple] = {}


def _distintivo(municipio: str) -> List[str]:
    """Las palabras que identifican al municipio en un texto.

    "General Madariaga" se nombra "Madariaga" en su propia prensa, asi que se
    usan las partes largas. Se sacan los tratamientos, que no distinguen: hay
    doce partidos que empiezan con "General".
    """
    nombre = _sin_tildes(municipio)
    partes = [
        p for p in nombre.split()
        if len(p) > 4 and p not in ("general", "coronel", "capitan", "adolfo", "carlos", "villa")
    ]
    return [nombre] + partes


def es_del_municipio(nota: Nota, municipio: str, regional: bool = False) -> bool:
    """La nota habla de ESTE municipio y no de otro.

    Hay dos regimenes, porque la prensa local y la regional escriben distinto.

    **Medio local** (cubre un solo partido): su tema por defecto ES su pueblo.
    Un diario de Chascomus escribe para vecinos de Chascomus y dice "la ciudad"
    o "la laguna", no repite el nombre en cada nota. Exigir que lo nombre
    descartaba notas propias: de 252 quedaban 39, y entre las tiradas estaba
    "operativos de control en la laguna", que es el simbolo del lugar. Entonces
    se acepta por defecto y se descarta solo si la nota es de OTRA ciudad.

    **Medio regional** (Infozona cubre cuatro partidos, Criterio Online otros
    cuatro): ahi el defecto no sirve, porque "esta en Infozona" no dice de cual
    de los cuatro habla. Se exige que nombre al municipio.

    En los dos casos el criterio es necesario y no suficiente: lo termina de
    decidir el modelo con su cita.
    """
    texto = _sin_tildes(f"{nota.titulo} {nota.texto}")
    titulo = _sin_tildes(nota.titulo)
    propias = _distintivo(municipio)
    nombra = any(p in texto for p in propias)

    if regional:
        return nombra

    # Local: se descarta si el TITULO es de otro lugar y no nombra el propio.
    # Se mira el titulo y no el cuerpo porque una nota local puede mencionar de
    # paso a La Plata —"el ministro provincial anuncio"— sin dejar de ser local.
    if any(p in titulo for p in propias):
        return True
    if _CACHE_OTROS.get(municipio) is None:
        _CACHE_OTROS[municipio] = _otros_municipios(municipio)
    ajenas = AJENAS + _CACHE_OTROS[municipio]
    return not any(a in titulo for a in ajenas)


def notas_del_medio(medio: str, base: str, sesion=None) -> List[Nota]:
    """Todas las notas de interes de un medio, para todos los aspectos."""
    ses = sesion or requests.Session()
    api = api_wordpress(base, ses)
    if api is None:
        return []

    vistas = set()
    salida: List[Nota] = []
    for aspecto, terminos in CONSULTAS.items():
        for termino in terminos:
            for nota in buscar(medio, base, api, aspecto, termino, ses):
                # La misma nota puede salir en dos busquedas del mismo aspecto.
                if (nota.url, aspecto) in vistas:
                    continue
                vistas.add((nota.url, aspecto))
                salida.append(nota)
    return salida


__all__ = ["AJENAS", "CONSULTAS", "MESES", "Nota", "api_wordpress", "buscar",
           "es_del_municipio", "notas_del_medio"]
