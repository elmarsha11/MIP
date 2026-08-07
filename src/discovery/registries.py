"""
Capa 2 - Registros oficiales provinciales.

Fuentes de primera mano que publican una pagina por municipio. No dependen de
buscadores ni de adivinar dominios.

  SIBOM  - Sistema de Boletin Oficial Municipal de la Provincia de Buenos Aires.
           https://sibom.slyt.gba.gob.ar/cities lista los municipios adheridos con
           su boletin. Da el tipo boletin_sibom con evidencia oficial.

  GBA    - https://www.gba.gob.ar/municipios/{slug}, ficha provincial del municipio.

El indice se descarga una sola vez por corrida y se cachea en disco.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:  # ejecutado como paquete
    from .schemas import (
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        ahora_iso,
        normalizar_slug,
    )
    from .site_crawler import consultar_html
    from .validator import consultar
except ImportError:  # ejecutado como script
    from schemas import (  # type: ignore[no-redef]
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        ahora_iso,
        normalizar_slug,
    )
    from site_crawler import consultar_html  # type: ignore[no-redef]
    from validator import consultar  # type: ignore[no-redef]

SIBOM_INDICE = "https://sibom.slyt.gba.gob.ar/cities"
GBA_FICHA = "https://www.gba.gob.ar/municipios/{slug}"

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "discovery" / "cache"
CACHE_SIBOM = CACHE_DIR / "indice_sibom.json"

# Nombres que el SIBOM escribe distinto al Gold Standard. Verificado contra el
# indice real (135 municipios) el 2026-08-07.
ALIAS_SIBOM = {
    "alem": "leandronalem",
    "gonzaleschaves": "adolfogonzaleschaves",
    "sanmigueldelmonte": "monte",
    "9dejulio": "nuevedejulio",
}

# Dominios que aparecen en toda ficha del SIBOM y son de la Provincia, no del
# municipio. Se excluyen al buscar el enlace al sitio municipal.
DOMINIOS_PROVINCIALES = (
    "gba.gob.ar", "gba.gov.ar", "arba.gov.ar", "facebook.com/baprovincia",
    "twitter.com/baprovincia", "instagram.com/provinciaba", "youtube.com",
    "twitter.com", "instagram.com", "facebook.com",
)

_indice_memoria: Optional[Dict[str, str]] = None


def cargar_indice_sibom(refrescar: bool = False) -> Dict[str, str]:
    """slug de municipio -> URL de su boletin en SIBOM."""
    global _indice_memoria
    if _indice_memoria is not None and not refrescar:
        return _indice_memoria

    if CACHE_SIBOM.exists() and not refrescar:
        try:
            _indice_memoria = json.loads(CACHE_SIBOM.read_text(encoding="utf-8"))
            return _indice_memoria
        except (json.JSONDecodeError, OSError):
            pass

    html = consultar_html(SIBOM_INDICE, timeout=25)
    indice: Dict[str, str] = {}
    if html:
        sopa = BeautifulSoup(html, "html.parser")
        for ancla in sopa.find_all("a", href=True):
            if "/cities/" not in ancla["href"]:
                continue
            nombre = " ".join(ancla.get_text(" ", strip=True).split())
            if not nombre:
                continue
            indice[normalizar_slug(nombre)] = urljoin(SIBOM_INDICE, ancla["href"])
    if indice:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_SIBOM.write_text(
                json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
    _indice_memoria = indice
    return indice


def buscar_en_sibom(municipio: str) -> Optional[str]:
    indice = cargar_indice_sibom()
    slug = normalizar_slug(municipio)
    if slug in indice:
        return indice[slug]
    alias = ALIAS_SIBOM.get(slug)
    if alias and alias in indice:
        return indice[alias]
    # el SIBOM a veces antepone el nombre completo ("Adolfo Gonzales Chaves")
    coincidencias = [v for k, v in indice.items() if slug and slug in k]
    return coincidencias[0] if len(coincidencias) == 1 else None


WIKIDATA_API = "https://www.wikidata.org/w/api.php"
CACHE_WIKIDATA = CACHE_DIR / "sitios_wikidata.json"
PROP_SITIO_OFICIAL = "P856"

_wikidata_memoria: Optional[Dict[str, Optional[str]]] = None


def _cache_wikidata() -> Dict[str, Optional[str]]:
    global _wikidata_memoria
    if _wikidata_memoria is None:
        try:
            _wikidata_memoria = json.loads(CACHE_WIKIDATA.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _wikidata_memoria = {}
    return _wikidata_memoria


def _guardar_cache_wikidata() -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_WIKIDATA.write_text(
            json.dumps(_cache_wikidata(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def sitio_oficial_desde_wikidata(municipio: str) -> Optional[str]:
    """Sitio oficial del partido segun Wikidata (propiedad P856).

    Wikidata NO es evidencia: es una pista. La URL que devuelve se acredita
    despues por HTTP, titulo y guardia de provincia, igual que cualquier dominio
    adivinado. Lo que se guarda como titulo_fragmento es el titulo real del sitio,
    nunca lo que dice Wikidata (ADR-0009).

    Resuelve municipios que ningun patron encuentra: Rauch esta en
    rauch.mun.gba.gov.ar y Tordillo en tordillomunicipio.org.
    """
    import requests

    cache = _cache_wikidata()
    clave = normalizar_slug(municipio)
    if clave in cache:
        return cache[clave]

    cabeceras = {"User-Agent": "MIP-Fase3/0.1 (relevamiento municipal PBA)"}
    sitio: Optional[str] = None
    try:
        busqueda = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": f"Partido de {municipio}",
                "language": "es",
                "format": "json",
                "limit": 3,
            },
            headers=cabeceras,
            timeout=20,
        ).json()

        for candidato in busqueda.get("search", []):
            etiqueta = normalizar_slug(candidato.get("label", ""))
            # La entidad tiene que nombrar al municipio: evita traer un homonimo
            # o una persona con el mismo apellido.
            if clave not in etiqueta:
                continue
            entidad = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": candidato["id"],
                    "props": "claims",
                    "format": "json",
                },
                headers=cabeceras,
                timeout=20,
            ).json()
            reclamos = entidad["entities"][candidato["id"]]["claims"].get(PROP_SITIO_OFICIAL)
            if reclamos:
                sitio = reclamos[0]["mainsnak"]["datavalue"]["value"]
                break
    except Exception:
        return None  # es una pista opcional; si falla, el pipeline sigue

    if sitio:
        # Solo se cachea el acierto. Un None puede ser "Wikidata no lo tiene" o
        # "la API se cayo en esta corrida"; guardarlo congelaria el error para
        # siempre y el municipio quedaria sin sitio sin motivo real.
        cache[clave] = sitio
        _guardar_cache_wikidata()
    return sitio


def pistas_de_sitio_oficial(municipio: str) -> List[str]:
    """URLs que otros registros publican como sitio del municipio, en orden de peso.

    Primero el SIBOM (registro de la propia Provincia), despues Wikidata.
    Ninguna se guarda sin acreditar por HTTP.
    """
    pistas: List[str] = []
    for fuente in (sitio_oficial_desde_sibom, sitio_oficial_desde_wikidata):
        try:
            url = fuente(municipio)
        except Exception:
            url = None
        if url and url not in pistas:
            pistas.append(url)
    return pistas


def sitio_oficial_desde_sibom(municipio: str) -> Optional[str]:
    """Extrae de la ficha SIBOM del municipio el enlace a su sitio web.

    Es la fuente mas confiable para los municipios cuyo dominio no se puede
    adivinar desde el nombre: la Provincia publica que Villa Gesell es
    gesell.gob.ar y Monte Hermoso es montehermoso.gov.ar.
    """
    ficha = buscar_en_sibom(municipio)
    if not ficha:
        return None
    html = consultar_html(ficha, timeout=20)
    if not html:
        return None

    sopa = BeautifulSoup(html, "html.parser")
    for ancla in sopa.find_all("a", href=True):
        href = ancla["href"].strip()
        if not href.startswith("http"):
            continue
        if any(d in href.lower() for d in DOMINIOS_PROVINCIALES):
            continue
        # No se fuerza a https: hay municipios que solo sirven http y convertir
        # la URL la mataria (ADR-0012). El esquema lo decide descubrir_dominio_oficial.
        return href.rstrip("/") + "/"
    return None


def urls_de_registros(
    municipio: str, id_municipio: str, fecha: Optional[str] = None
) -> List[DiscoveryURL]:
    """URLs oficiales del municipio en registros provinciales."""
    fecha = fecha or ahora_iso()
    encontradas: List[DiscoveryURL] = []

    url_sibom = buscar_en_sibom(municipio)
    if url_sibom:
        encontradas.append(
            DiscoveryURL(
                municipio=municipio,
                id_municipio=id_municipio,
                url=url_sibom,
                tipo=TipoURL.BOLETIN_SIBOM,
                fuente_query=f"registro_sibom:{SIBOM_INDICE}",
                titulo_fragmento=(
                    f"{municipio} - Sistema de Boletin Oficial Municipal (SIBOM), "
                    "Provincia de Buenos Aires"
                ),
                fecha_descubrimiento=fecha,
                confianza=Confianza.MEDIA,
                estado_validacion=EstadoValidacion.PENDIENTE,
                es_oficial=True,
            )
        )

    url_gba = GBA_FICHA.format(slug=normalizar_slug(municipio))
    resp = consultar(url_gba, timeout=12)
    if resp.status is not None and resp.status < 400 and resp.titulo:
        # La ficha provincial existe solo si el titulo nombra al municipio;
        # gba.gob.ar responde 200 con "Pagina no encontrada" para los que no estan.
        if normalizar_slug(municipio) in normalizar_slug(resp.titulo):
            encontradas.append(
                DiscoveryURL(
                    municipio=municipio,
                    id_municipio=id_municipio,
                    url=url_gba,
                    tipo=TipoURL.OTRO,
                    fuente_query="registro_gba:gba.gob.ar/municipios",
                    titulo_fragmento=f"{resp.titulo} - ficha oficial de la Provincia",
                    fecha_descubrimiento=fecha,
                    confianza=Confianza.MEDIA,
                    estado_validacion=EstadoValidacion.VALIDADA,
                    es_oficial=True,
                )
            )
    return encontradas


__all__ = [
    "GBA_FICHA",
    "SIBOM_INDICE",
    "buscar_en_sibom",
    "cargar_indice_sibom",
    "urls_de_registros",
]
