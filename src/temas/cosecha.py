"""
Que paginas leer para responder un tema.

Fase 3 clasifica las URLs en 11 tipos y ninguno es tematico: descubrio el portal
y el boletin, no la pagina de residuos. Buscar el tema solo en lo ya clasificado
da casi nada — de 708 URLs descubiertas, 6 rozaban lo ambiental y la mitad eran
tasas de higiene, que son un impuesto y no una politica.

Por eso la cosecha tiene tres patas, de mas barata a mas cara:

1. **Lo ya descubierto** que sirve al tema: portal, tramites, ordenanzas y
   boletin. `urls_de_municipio` de Fase 4 no alcanza porque deduplica a una
   pagina por tipo y deja SIBOM afuera.
2. **El portal, recorrido con las senales del tema.** Es la misma cosecha
   dirigida que Fase 4 usa para turnos, generalizada: entra al home y sigue los
   enlaces cuyo texto o URL hablan del tema. Ahi vive la pagina de residuos.
3. **Prensa local**, si se pide. Va marcada aparte: prueba que algo paso, no que
   exista politica municipal.

La cosecha solo elige QUE leer. Lo que digan lo sigue decidiendo el modelo con
cita verificada: mejora el recall, no fabrica el dato.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Sequence
from urllib.parse import urljoin, urlparse

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
for _ruta in (_AQUI, _SRC / "extraction", _SRC / "seguridad"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from fetcher import (  # noqa: E402
    SQLITE_DISCOVERY,
    URLCandidata,
    descargar,
)
from modelos import normalizar_para_cotejo  # noqa: E402

from rastreo import Tema, TipoEvidencia  # noqa: E402

# Tipos de Fase 3 que sirven a cualquier tema, y con que clase de evidencia
# entran. El boletin y las ordenanzas prueban decision municipal; el portal
# prueba que el municipio lo publica.
TIPOS_BASE = {
    "sitio_oficial": TipoEvidencia.OFICIAL,
    "tramites": TipoEvidencia.OFICIAL,
    "transparencia": TipoEvidencia.OFICIAL,
    "normativa_ordenanzas": TipoEvidencia.NORMATIVA,
    "boletin_sibom": TipoEvidencia.NORMATIVA,
}

MAX_ENLACES_COSECHADOS = 6
MAX_PAGINAS = 12
MAX_BYTES_HTML = 400_000
TIMEOUT = 20


class PaginaTema(NamedTuple):
    """Una pagina lista para el prompt, con la clase de evidencia que aporta."""

    url: str
    tipo: str
    confianza_url: str
    texto: str
    tipo_evidencia: TipoEvidencia


def urls_base(
    municipio: str,
    tema: Tema,
    sqlite_path: Path = SQLITE_DISCOVERY,
) -> List[URLCandidata]:
    """URLs ya descubiertas que sirven al tema.

    Trae los tipos utiles a cualquier tema, mas cualquier URL —del tipo que
    sea— cuyo texto o direccion mencione una senal del tema. Esa segunda regla
    es la que rescata el digesto ambiental de Laprida, que Fase 3 archivo como
    "otro".
    """
    if not Path(sqlite_path).exists():
        raise FileNotFoundError(
            f"No existe {sqlite_path}. Corre Fase 3 primero: "
            "python src/discovery/discovery_engine.py --all"
        )

    con = sqlite3.connect(sqlite_path)
    try:
        filas = con.execute(
            "SELECT url, tipo, confianza, COALESCE(titulo_fragmento, '') "
            "FROM discovery_urls WHERE municipio = ?",
            (municipio,),
        ).fetchall()
    finally:
        con.close()

    senales = [normalizar_para_cotejo(s) for s in tema.senales]
    elegidas: List[URLCandidata] = []
    vistas = set()

    for url, tipo, confianza, titulo in filas:
        clave = (url or "").rstrip("/").lower()
        if not clave or clave in vistas:
            continue

        del_tema = any(s in normalizar_para_cotejo(f"{url} {titulo}") for s in senales)
        if tipo not in TIPOS_BASE and not del_tema:
            continue

        vistas.add(clave)
        elegidas.append(URLCandidata(url=url, tipo=tipo, confianza=confianza or "Media"))

    # Primero lo que prueba decision (normativa), despues lo que prueba difusion.
    orden_tipo = {"normativa_ordenanzas": 0, "boletin_sibom": 1, "sitio_oficial": 2}
    orden_conf = {"Alta": 0, "Media": 1, "Baja": 2}
    elegidas.sort(
        key=lambda c: (orden_tipo.get(c.tipo, 5), orden_conf.get(c.confianza, 9))
    )
    return elegidas


def enlaces_del_tema(
    html: str,
    url_base: str,
    tema: Tema,
    ya_leidas: Sequence[str] = (),
    maximo: int = MAX_ENLACES_COSECHADOS,
) -> List[URLCandidata]:
    """Enlaces del portal cuyo texto o direccion hablan del tema.

    Generaliza `paginas_de_turnos` de Fase 4. Solo sigue enlaces del mismo host:
    un municipio que linkea a OPDS no convierte a OPDS en fuente municipal.
    """
    from bs4 import BeautifulSoup

    host = (urlparse(url_base).hostname or "").lower()
    if not host:
        return []

    senales = [normalizar_para_cotejo(s) for s in tema.senales]
    descartadas = {u.rstrip("/").lower() for u in ya_leidas}
    vistos = set()
    encontrados: List[URLCandidata] = []

    for ancla in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        destino = urljoin(url_base, ancla["href"]).split("#")[0]
        if (urlparse(destino).hostname or "").lower() != host:
            continue

        clave = destino.rstrip("/").lower()
        if clave in vistos or clave in descartadas:
            continue

        texto = ancla.get_text(" ", strip=True)
        objetivo = normalizar_para_cotejo(f"{destino} {texto}")
        if not any(s in objetivo for s in senales):
            continue

        vistos.add(clave)
        encontrados.append(
            URLCandidata(url=destino, tipo="tema_cosechado", confianza="Media")
        )
        if len(encontrados) >= maximo:
            break

    return encontrados


def _traer_html(url: str) -> Optional[str]:
    try:
        import requests

        from fetcher import _sesion

        resp = _sesion().get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
        crudo = resp.raw.read(MAX_BYTES_HTML, decode_content=True) or b""
        resp.close()
        if resp.status_code >= 400:
            return None
        return crudo.decode(resp.encoding or "utf-8", errors="replace")
    except Exception:
        return None


def notas_de_prensa(
    municipio: str,
    tema: Tema,
    buscador: Optional[Callable] = None,
    maximo: int = 4,
) -> List[PaginaTema]:
    """Notas de medios locales que mencionan las senales del tema.

    Se inyecta el buscador para poder testear sin red. Por defecto usa el motor
    de prensa que ya existe en src/seguridad.
    """
    if buscador is None:
        return []

    paginas: List[PaginaTema] = []
    for nota in buscador(municipio, tema) or []:
        texto = getattr(nota, "texto", "") or ""
        if len(texto) < 80:
            continue
        paginas.append(
            PaginaTema(
                url=getattr(nota, "url", ""),
                tipo="prensa",
                confianza_url="Media",
                texto=texto,
                tipo_evidencia=TipoEvidencia.PRENSA,
            )
        )
        if len(paginas) >= maximo:
            break
    return paginas


def paginas_del_tema(
    municipio: str,
    tema: Tema,
    sqlite_path: Path = SQLITE_DISCOVERY,
    con_prensa: bool = False,
    buscador_prensa: Optional[Callable] = None,
    bajar: Callable = descargar,
    traer_html: Callable = _traer_html,
    maximo: int = MAX_PAGINAS,
) -> List[PaginaTema]:
    """Las paginas que se le van a mostrar al modelo, en orden de utilidad."""
    candidatas = urls_base(municipio, tema, sqlite_path)

    # Cosecha dirigida sobre el portal: ahi esta la pagina que Fase 3 no clasifico.
    home = next((c for c in candidatas if c.tipo == "sitio_oficial"), None)
    if home is not None:
        html = traer_html(home.url)
        if html:
            candidatas += enlaces_del_tema(
                html, home.url, tema, ya_leidas=[c.url for c in candidatas]
            )

    paginas: List[PaginaTema] = []
    for candidata in candidatas:
        if len(paginas) >= maximo:
            break
        bajada = bajar(candidata)
        if bajada is None:
            continue
        paginas.append(
            PaginaTema(
                url=bajada.url,
                tipo=bajada.tipo,
                confianza_url=bajada.confianza_url,
                texto=bajada.texto,
                tipo_evidencia=TIPOS_BASE.get(candidata.tipo, TipoEvidencia.OFICIAL),
            )
        )

    if con_prensa:
        paginas += notas_de_prensa(municipio, tema, buscador_prensa)

    return paginas


__all__ = [
    "MAX_PAGINAS",
    "PaginaTema",
    "enlaces_del_tema",
    "notas_de_prensa",
    "paginas_del_tema",
    "urls_base",
]
