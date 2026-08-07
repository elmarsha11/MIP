"""
Capa 2 - Busqueda web (~1,5 min por municipio).

Ejecuta las 8 queries del HANDOFF contra un buscador y convierte cada resultado en
un DiscoveryURL tipificado. Aca nace la evidencia: el titulo y el snippet que
devuelve el buscador son el titulo_fragmento que exige ADR-0009.

Proveedor: DuckDuckGo HTML endpoint (sin API key, sin cuenta). Se eligio sobre
Google/Bing porque no exige clave, no bloquea de entrada y devuelve titulo +
snippet parseables. La interfaz esta abierta: implementar otro proveedor es
implementar buscar().

Cache: toda respuesta cruda se guarda en data/processed/discovery/cache/. Sirve
para tres cosas: no re-consultar en cada corrida, poder correr offline, y dejar
auditable de donde salio cada fragmento (trazabilidad, Principio P3).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

try:  # ejecutado como paquete
    from .schemas import (
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        ahora_iso,
        normalizar_slug,
        normalizar_texto,
    )
except ImportError:  # ejecutado como script
    from schemas import (  # type: ignore[no-redef]
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        ahora_iso,
        normalizar_slug,
        normalizar_texto,
    )

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

DDG_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
TIMEOUT_SEGUNDOS = 25
TOP_N_POR_QUERY = 5  # HANDOFF: "guarda top 5 resultados por query"
INTERVALO_MINIMO_SEGUNDOS = 1.5  # cortesia con el buscador
MAX_REINTENTOS = 3

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "discovery" / "cache"

# Las 8 queries del HANDOFF seccion 4 / Fase3_Plan_Descubrimiento.md.
# {nombre} se reemplaza por el nombre exacto del Gold Standard.
PLANTILLAS_QUERY: Sequence[str] = (
    "Municipalidad de {nombre} Buenos Aires sitio oficial",
    "Municipalidad de {nombre} transparencia boletin SIBOM",
    "Municipalidad de {nombre} turnos salud online",
    "Municipalidad de {nombre} Facebook oficial",
    "Municipalidad de {nombre} app Play Store",
    "{nombre} gob ar tramites",
    "{nombre} gob ar tasas pagos RAFAM",
    "{nombre} gob ar reclamos 147",
)


class ErrorBusqueda(RuntimeError):
    """El buscador no devolvio resultados utilizables."""


class ResultadoBusqueda(NamedTuple):
    url: str
    titulo: str
    snippet: str
    posicion: int
    query: str


# ---------------------------------------------------------------------------
# Tipificacion de URLs (enum cerrado de schemas/discovery_schema.md)
# ---------------------------------------------------------------------------

# Dominio -> tipo. Se evalua antes que los paths.
TIPOS_POR_DOMINIO = (
    ("facebook.com", TipoURL.FACEBOOK_OFICIAL),
    ("instagram.com", TipoURL.INSTAGRAM_OFICIAL),
    ("youtube.com", TipoURL.YOUTUBE_OFICIAL),
    ("play.google.com", TipoURL.PLAY_STORE),
    ("apps.apple.com", TipoURL.APP_STORE),
    ("itunes.apple.com", TipoURL.APP_STORE),
    ("sibom.slyt.gba.gob.ar", TipoURL.BOLETIN_SIBOM),
)

# (palabras en el path, tipo). Orden = prioridad; la primera que matchea gana.
TIPOS_POR_PATH = (
    (("transparencia", "gobierno-abierto", "gobiernoabierto", "datos-abiertos"), TipoURL.TRANSPARENCIA),
    (("boletin", "sibom", "digesto-boletin"), TipoURL.BOLETIN_SIBOM),
    (("licitacion", "compras", "contrataciones"), TipoURL.LICITACIONES),
    (("ordenanza", "normativa", "digesto", "decretos"), TipoURL.NORMATIVA_ORDENANZAS),
    (("turno", "salud", "caps", "hospital", "vacuna"), TipoURL.SALUD_TURNOS),
    (("rafam", "tasa", "renta", "pago", "autogestion", "cuenta-corriente", "tributaria"), TipoURL.HACIENDA_TASAS_RAFAM),
    (("reclamo", "147", "atencion-ciudadana", "atencionciudadana"), TipoURL.RECLAMOS_147),
    (("gde", "expediente", "mesa-de-entradas", "mesadeentradas", "tramites-a-distancia", "tad"), TipoURL.GDE_EXPEDIENTE),
    (("tramite", "servicios", "guia-de-tramites"), TipoURL.TRAMITES),
)

# Sitios que aparecen en las busquedas pero nunca son el municipio.
DOMINIOS_NO_MUNICIPALES = (
    "wikipedia.org", "govserv.org", "cybo.com", "paginasamarillas", "opendata",
    "linkedin.com", "twitter.com", "x.com", "tiktok.com", "yelp.", "foursquare.",
    "infobae.com", "lanacion.com.ar", "clarin.com", "pagina12.com.ar", "eldia.com",
    "zonaprop", "argenprop", "mercadolibre", "indeed.com", "computrabajo",
    "bing.com", "google.com/search", "duckduckgo.com", "youtube.com/results",
)

DOMINIOS_OFICIALES_SUFIJOS = (".gob.ar", ".gov.ar", ".mun.gba.gov.ar")


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _parece_slug_de_nota(path: str) -> bool:
    """Distingue una seccion del portal de una nota de prensa.

    '/tramites-y-servicios/'  -> seccion  (2 guiones)
    '/salud-para-todos-mas-de-380-vecinas-atendidas-en-el-caps/' -> nota

    Importa porque los portales WordPress redirigen /salud/ a la nota mas parecida,
    y esa nota terminaria tipificada como salud_turnos con confianza Alta.
    """
    ultimo = path.rstrip("/").rsplit("/", 1)[-1]
    return ultimo.count("-") >= 5 or len(ultimo) > 60


def clasificar_tipo(url: str, titulo: str = "", snippet: str = "") -> TipoURL:
    """Asigna un tipo del enum cerrado a una URL descubierta."""
    host = _host(url)
    for fragmento_host, tipo in TIPOS_POR_DOMINIO:
        if fragmento_host in host:
            return tipo

    parsed = urlparse(url)

    # Raiz de un dominio oficial = home del municipio. Se chequea ANTES que los
    # paths: una home no puede ser otra cosa.
    if parsed.path.strip("/") == "" and not parsed.query and es_dominio_oficial(url):
        return TipoURL.SITIO_OFICIAL

    ruta = f"{parsed.path}?{parsed.query}".lower()
    # Las notas de prensa mencionan cualquier tema; no son la seccion del tema.
    if any(p in ruta for p in ("/noticia", "/novedades", "/prensa", "/nota/", "/blog")):
        return TipoURL.OTRO
    if _parece_slug_de_nota(parsed.path):
        return TipoURL.OTRO
    for palabras, tipo in TIPOS_POR_PATH:
        if any(p in ruta for p in palabras):
            return tipo
    return TipoURL.OTRO


def es_dominio_oficial(url: str) -> bool:
    host = _host(url)
    return any(host.endswith(sufijo) for sufijo in DOMINIOS_OFICIALES_SUFIJOS)


def es_dominio_descartable(url: str) -> bool:
    url_lower = url.lower()
    return any(d in url_lower for d in DOMINIOS_NO_MUNICIPALES)


def evaluar_es_oficial(url: str, municipio: str, evidencia: str) -> Optional[bool]:
    """¿Parece oficial? None = todavia no se sabe (ADR-0009: desconocido no es False)."""
    slug = normalizar_slug(municipio)
    host = _host(url)
    if es_dominio_oficial(url) and slug and slug in normalizar_slug(host):
        return True
    if es_dominio_descartable(url):
        return False
    texto = normalizar_texto(evidencia)
    nombre = normalizar_texto(municipio)
    if nombre and nombre in texto and ("municipalidad" in texto or "municipio" in texto):
        # Ej: pagina de Facebook titulada "Municipalidad de Navarro". Parece oficial,
        # pero no esta verificado: lo confirma la Capa 3 o una persona.
        return None
    return None


def parece_del_municipio(url: str, municipio: str, evidencia: str) -> bool:
    """Filtro de pertinencia: descarta ruido antes de guardarlo.

    Ser un dominio .gob.ar no alcanza: arba.gov.ar y el SIBOM provincial son
    oficiales y no son de este municipio. Se exige que el municipio aparezca en
    la URL o en la evidencia. ADR-0009: sin nada que lo ate al municipio, no es
    un dato de ese municipio.
    """
    if es_dominio_descartable(url):
        return False
    slug = normalizar_slug(municipio)
    if slug and slug in normalizar_slug(_host(url) + urlparse(url).path):
        return True
    return normalizar_texto(municipio) in normalizar_texto(evidencia)


# ---------------------------------------------------------------------------
# Proveedor de busqueda
# ---------------------------------------------------------------------------


class _Throttle:
    """Un pedido cada INTERVALO_MINIMO_SEGUNDOS, compartido entre hilos."""

    def __init__(self, intervalo: float):
        self.intervalo = intervalo
        self._lock = threading.Lock()
        self._ultimo = 0.0

    def esperar(self) -> None:
        with self._lock:
            espera = self.intervalo - (time.monotonic() - self._ultimo)
            if espera > 0:
                time.sleep(espera)
            self._ultimo = time.monotonic()


class DuckDuckGoProvider:
    """Busqueda contra el endpoint HTML de DuckDuckGo, con cache en disco."""

    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        usar_cache: bool = True,
        offline: bool = False,
        intervalo: float = INTERVALO_MINIMO_SEGUNDOS,
    ):
        self.cache_dir = Path(cache_dir)
        self.usar_cache = usar_cache
        self.offline = offline  # solo cache, nunca sale a la red
        self._throttle = _Throttle(intervalo)
        self._sesion = requests.Session()
        self._sesion.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "es-AR,es;q=0.9",
                "Accept": "text/html,application/xhtml+xml",
            }
        )
        if self.usar_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- cache --------------------------------------------------------------

    def _path_cache(self, query: str) -> Path:
        clave = hashlib.sha1(query.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"q_{clave}.json"

    def _leer_cache(self, query: str) -> Optional[List[ResultadoBusqueda]]:
        if not self.usar_cache:
            return None
        path = self._path_cache(query)
        if not path.exists():
            return None
        try:
            datos = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return [
            ResultadoBusqueda(
                url=r["url"], titulo=r["titulo"], snippet=r["snippet"],
                posicion=r["posicion"], query=query,
            )
            for r in datos.get("resultados", [])
        ]

    def _escribir_cache(self, query: str, resultados: List[ResultadoBusqueda]) -> None:
        if not self.usar_cache:
            return
        payload = {
            "query": query,
            "fecha": ahora_iso(),
            "proveedor": "duckduckgo_html",
            "resultados": [
                {"url": r.url, "titulo": r.titulo, "snippet": r.snippet, "posicion": r.posicion}
                for r in resultados
            ],
        }
        try:
            self._path_cache(query).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # el cache es una optimizacion, no puede tumbar el pipeline

    # -- red ----------------------------------------------------------------

    @staticmethod
    def _limpiar_url(href: str) -> Optional[str]:
        """DDG envuelve los links en /l/?uddg=<url encodeada>."""
        if not href:
            return None
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if "duckduckgo.com" in (parsed.hostname or "") and parsed.path.startswith("/l/"):
            destino = parse_qs(parsed.query).get("uddg", [""])[0]
            href = unquote(destino) if destino else ""
        if not href.startswith("http"):
            return None
        return href.split("#")[0]

    def _parsear(self, html: str, query: str) -> List[ResultadoBusqueda]:
        sopa = BeautifulSoup(html, "html.parser")
        resultados: List[ResultadoBusqueda] = []
        for i, bloque in enumerate(sopa.select("div.result"), start=1):
            ancla = bloque.select_one("a.result__a")
            if ancla is None:
                continue
            url = self._limpiar_url(ancla.get("href", ""))
            if not url:
                continue
            snippet_tag = bloque.select_one(".result__snippet")
            resultados.append(
                ResultadoBusqueda(
                    url=url,
                    titulo=ancla.get_text(" ", strip=True),
                    snippet=snippet_tag.get_text(" ", strip=True) if snippet_tag else "",
                    posicion=i,
                    query=query,
                )
            )
        return resultados

    def buscar(self, query: str, top_n: int = TOP_N_POR_QUERY) -> List[ResultadoBusqueda]:
        """Devuelve hasta top_n resultados. Lista vacia si el buscador no responde."""
        cacheados = self._leer_cache(query)
        if cacheados is not None:
            return cacheados[:top_n]
        if self.offline:
            return []

        ultimo_error: Optional[Exception] = None
        for intento in range(1, MAX_REINTENTOS + 1):
            self._throttle.esperar()
            try:
                resp = self._sesion.post(
                    DDG_URL, data={"q": query, "kl": "ar-es"}, timeout=TIMEOUT_SEGUNDOS
                )
                if resp.status_code in (202, 403, 429):
                    raise ErrorBusqueda(f"buscador limitando ({resp.status_code})")
                resp.raise_for_status()
                resultados = self._parsear(resp.text, query)
                if not resultados and "anomaly" in resp.text.lower():
                    raise ErrorBusqueda("buscador pidio verificacion anti-bot")
                self._escribir_cache(query, resultados)
                return resultados[:top_n]
            except (requests.RequestException, ErrorBusqueda) as exc:
                ultimo_error = exc
                if intento < MAX_REINTENTOS:
                    # backoff exponencial con jitter
                    time.sleep(min(2 ** intento + random.uniform(0, 1.5), 20))

        # ADR-0009: si el buscador no respondio, no hay dato. No se inventa nada.
        print(f"    [busqueda fallida] {query!r}: {ultimo_error}")
        return []


class ProveedorFijo:
    """Proveedor de resultados predefinidos. Para tests, sin red."""

    def __init__(self, respuestas: Dict[str, List[ResultadoBusqueda]]):
        self.respuestas = respuestas
        self.queries_ejecutadas: List[str] = []

    def buscar(self, query: str, top_n: int = TOP_N_POR_QUERY) -> List[ResultadoBusqueda]:
        self.queries_ejecutadas.append(query)
        return self.respuestas.get(query, [])[:top_n]


# ---------------------------------------------------------------------------
# Capa 2
# ---------------------------------------------------------------------------


def construir_queries(municipio: str) -> List[str]:
    return [plantilla.format(nombre=municipio) for plantilla in PLANTILLAS_QUERY]


def _fragmento(resultado: ResultadoBusqueda) -> str:
    """Titulo + snippet, recortado. Es la evidencia literal que exige ADR-0009."""
    partes = [p for p in (resultado.titulo, resultado.snippet) if p]
    texto = re.sub(r"\s+", " ", " - ".join(partes)).strip()
    return texto[:500]


def buscar_urls(
    municipio: str,
    id_municipio: str,
    proveedor=None,
    fecha: Optional[str] = None,
    top_n: int = TOP_N_POR_QUERY,
) -> List[DiscoveryURL]:
    """Ejecuta las 8 queries y devuelve las URLs con evidencia.

    Toda URL de esta capa sale con confianza Media y estado pendiente: tiene
    evidencia textual, pero nadie verifico todavia que responda. La Capa 3
    decide si sube a Alta o baja a error_404.
    """
    proveedor = proveedor or DuckDuckGoProvider()
    fecha = fecha or ahora_iso()

    urls: List[DiscoveryURL] = []
    vistas = set()
    for query in construir_queries(municipio):
        for resultado in proveedor.buscar(query, top_n=top_n):
            clave = resultado.url.rstrip("/").lower()
            if clave in vistas:
                continue

            evidencia = _fragmento(resultado)
            if not evidencia:
                continue  # ADR-0009: sin fragmento no hay URL valida
            if not parece_del_municipio(resultado.url, municipio, evidencia):
                continue

            vistas.add(clave)
            tipo = clasificar_tipo(resultado.url, resultado.titulo, resultado.snippet)
            try:
                urls.append(
                    DiscoveryURL(
                        municipio=municipio,
                        id_municipio=id_municipio,
                        url=resultado.url,
                        tipo=tipo,
                        fuente_query=query,
                        titulo_fragmento=evidencia,
                        fecha_descubrimiento=fecha,
                        confianza=Confianza.MEDIA,
                        estado_validacion=EstadoValidacion.PENDIENTE,
                        es_oficial=evaluar_es_oficial(resultado.url, municipio, evidencia),
                    )
                )
            except ValueError:
                # No cumple el schema (ej: play_store sin id de app). Se descarta,
                # no se fuerza. Preferimos 0 URLs a una URL que miente.
                continue
    return urls


__all__ = [
    "PLANTILLAS_QUERY",
    "TOP_N_POR_QUERY",
    "DuckDuckGoProvider",
    "ErrorBusqueda",
    "ProveedorFijo",
    "ResultadoBusqueda",
    "buscar_urls",
    "clasificar_tipo",
    "construir_queries",
    "es_dominio_oficial",
    "evaluar_es_oficial",
    "parece_del_municipio",
]
