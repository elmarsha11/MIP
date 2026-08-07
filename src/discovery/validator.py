"""
Capa 3 - Validacion (~30 s por municipio).

Sale a la red y confirma cada URL candidata:
    1. Responde 200?
    2. La URL contiene el nombre del municipio o gob.ar?
    3. El <title> dice "Municipalidad de {nombre}"?

Confianza resultante (HANDOFF seccion 4 / Fase3_Plan_Descubrimiento.md):
    2 y 3 -> Alta      2 sin 3 -> Media      ninguna -> Baja

Regla que manda sobre todo lo anterior (ADR-0009): si no se pudo leer un titulo,
la URL se queda sin fragmento y por lo tanto no puede pasar de Baja/no_verificable.
Una URL heuristica que nunca consiguio evidencia sigue siendo una hipotesis, no un dato.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, NamedTuple, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:  # ejecutado como paquete
    from .schemas import (
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        normalizar_slug,
        normalizar_texto,
        variantes_slug,
    )
    from .search_provider import USER_AGENT, clasificar_tipo, es_dominio_oficial
except ImportError:  # ejecutado como script
    from schemas import (  # type: ignore[no-redef]
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        normalizar_slug,
        normalizar_texto,
        variantes_slug,
    )
    from search_provider import (  # type: ignore[no-redef]
        USER_AGENT,
        clasificar_tipo,
        es_dominio_oficial,
    )

TIMEOUT_SEGUNDOS = 15
MAX_BYTES_HTML = 300_000  # con el <head> alcanza; no bajamos portales enteros
WORKERS_POR_MUNICIPIO = 6

# Tipos que no se validan con HTTP: las redes sociales y las stores responden
# 200 con muros de login o paginas genericas, asi que el codigo de estado no
# prueba nada. Se dejan como vinieron de la Capa 2 (Media/pendiente).
TIPOS_SIN_VALIDACION_HTTP = frozenset(
    {
        TipoURL.FACEBOOK_OFICIAL,
        TipoURL.INSTAGRAM_OFICIAL,
        TipoURL.YOUTUBE_OFICIAL,
        TipoURL.PLAY_STORE,
        TipoURL.APP_STORE,
    }
)

_local = threading.local()


def _sesion() -> requests.Session:
    """Una Session por hilo (requests.Session no es thread-safe)."""
    if not hasattr(_local, "sesion"):
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-AR,es;q=0.9"})
        _local.sesion = s
    return _local.sesion


class RespuestaHTTP(NamedTuple):
    status: Optional[int]
    url_final: str
    titulo: Optional[str]
    error: Optional[str]


def extraer_titulo(html: str) -> Optional[str]:
    """<title>, con fallback a og:title y h1."""
    sopa = BeautifulSoup(html, "html.parser")
    if sopa.title and sopa.title.string:
        titulo = re.sub(r"\s+", " ", sopa.title.string).strip()
        if titulo:
            return titulo[:300]
    og = sopa.find("meta", property="og:title")
    if og and og.get("content"):
        return re.sub(r"\s+", " ", og["content"]).strip()[:300]
    h1 = sopa.find("h1")
    if h1:
        texto = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)).strip()
        if texto:
            return texto[:300]
    return None


def consultar(url: str, timeout: int = TIMEOUT_SEGUNDOS) -> RespuestaHTTP:
    """GET con redirects. No levanta excepciones: las devuelve como dato."""
    try:
        resp = _sesion().get(url, timeout=timeout, allow_redirects=True, stream=True)
        contenido = resp.raw.read(MAX_BYTES_HTML, decode_content=True) or b""
        resp.close()
        encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        html = contenido.decode(encoding, errors="replace")
        titulo = extraer_titulo(html) if resp.status_code < 400 else None
        return RespuestaHTTP(resp.status_code, resp.url, titulo, None)
    except requests.RequestException as exc:
        return RespuestaHTTP(None, url, None, type(exc).__name__)


# ---------------------------------------------------------------------------
# Reglas de confianza
# ---------------------------------------------------------------------------


def url_apunta_al_municipio(url: str, municipio: str) -> bool:
    """Criterio 2: la URL nombra al municipio, o es un dominio oficial.

    Se aceptan las variantes cortas del nombre: areco.ar es de San Antonio de
    Areco y madariaga.gob.ar es de General Madariaga.
    """
    parsed = urlparse(url)
    objetivo = normalizar_slug((parsed.hostname or "") + parsed.path)
    if any(v and v in objetivo for v in variantes_slug(municipio)):
        return True
    return es_dominio_oficial(url)


def titulo_es_del_municipio(titulo: Optional[str], municipio: str) -> bool:
    """Criterio 3: el titulo evidencia que es la municipalidad de ESE municipio."""
    if not titulo:
        return False
    texto = normalizar_texto(titulo)
    nombre = normalizar_texto(municipio)
    if nombre not in texto:
        return False
    return any(p in texto for p in ("municipalidad", "municipio", "municipal", "gobierno"))


def calcular_confianza(url: str, municipio: str, titulo: Optional[str]) -> Confianza:
    coincide_url = url_apunta_al_municipio(url, municipio)
    coincide_titulo = titulo_es_del_municipio(titulo, municipio)
    if coincide_url and coincide_titulo:
        return Confianza.ALTA
    if coincide_url:
        return Confianza.MEDIA
    return Confianza.BAJA


# ---------------------------------------------------------------------------
# Validacion de una URL
# ---------------------------------------------------------------------------


def validar(url_candidata: DiscoveryURL, timeout: int = TIMEOUT_SEGUNDOS) -> DiscoveryURL:
    """Devuelve una copia de la URL con confianza y estado actualizados.

    Nunca sube la confianza sin evidencia: el titulo leido de la pagina pasa a ser
    el titulo_fragmento cuando la candidata no traia uno.
    """
    if url_candidata.tipo in TIPOS_SIN_VALIDACION_HTTP:
        return url_candidata

    resp = consultar(url_candidata.url, timeout=timeout)

    # -- caso 1: no respondio o dio error ----------------------------------
    if resp.status is None or resp.status >= 400:
        estado = (
            EstadoValidacion.ERROR_404
            if resp.status == 404
            else EstadoValidacion.NO_ENCONTRADO
            if resp.status is None
            else EstadoValidacion.NO_VERIFICABLE
        )
        # La evidencia previa (si venia de la Capa 2) se conserva: existio.
        # Lo que baja es la confianza, porque hoy la URL no responde.
        return url_candidata.model_copy(
            update={
                "confianza": Confianza.BAJA,
                "estado_validacion": estado,
                "es_oficial": url_candidata.es_oficial if url_candidata.titulo_fragmento else None,
            }
        )

    # -- caso 2: respondio pero no se pudo leer titulo ----------------------
    fragmento = resp.titulo or url_candidata.titulo_fragmento
    if not fragmento:
        # ADR-0009: responde 200 pero no hay una sola linea de evidencia.
        return url_candidata.model_copy(
            update={
                "confianza": Confianza.BAJA,
                "estado_validacion": EstadoValidacion.NO_VERIFICABLE,
                "es_oficial": None,
            }
        )

    # -- caso 3: respondio con titulo --------------------------------------
    # No se fuerza https: hay municipios sin TLS y convertir la URL la mataria.
    url_final = resp.url_final.split("#")[0]

    confianza = calcular_confianza(url_final, url_candidata.municipio, resp.titulo)
    es_oficial = (
        True
        if confianza is Confianza.ALTA
        else url_candidata.es_oficial
    )

    campos = url_candidata.model_dump()
    campos.update(
        url=url_final,
        titulo_fragmento=fragmento,
        confianza=confianza,
        estado_validacion=EstadoValidacion.VALIDADA,
        es_oficial=es_oficial,
        id="",  # se recalcula: la URL final puede diferir de la candidata
    )
    # Si hubo redirect, el tipo se decide sobre la URL que quedo, no sobre la
    # que se pidio: /salud/ puede terminar en una nota de prensa.
    if url_final.rstrip("/") != url_candidata.url.rstrip("/"):
        campos["tipo"] = clasificar_tipo(url_final, resp.titulo or "")
    try:
        return DiscoveryURL.model_validate(campos)
    except ValueError:
        # El resultado no cumple el schema (tipico: Alta cuyo fragmento no menciona
        # al municipio). Se degrada a Media, nunca se fuerza hacia arriba.
        campos.update(confianza=Confianza.MEDIA, es_oficial=url_candidata.es_oficial)
        try:
            return DiscoveryURL.model_validate(campos)
        except ValueError:
            return url_candidata


def validar_lote(
    urls: List[DiscoveryURL],
    workers: int = WORKERS_POR_MUNICIPIO,
    timeout: int = TIMEOUT_SEGUNDOS,
) -> List[DiscoveryURL]:
    """Valida en paralelo conservando el orden de entrada."""
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(urls)))) as pool:
        return list(pool.map(lambda u: validar(u, timeout=timeout), urls))


__all__ = [
    "RespuestaHTTP",
    "TIPOS_SIN_VALIDACION_HTTP",
    "calcular_confianza",
    "consultar",
    "extraer_titulo",
    "titulo_es_del_municipio",
    "url_apunta_al_municipio",
    "validar",
    "validar_lote",
]
