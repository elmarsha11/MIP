"""
Fase 4 - Lectura de las paginas que encontro Fase 3.

No busca ni adivina nada: toma las URLs ya tipificadas y validadas en
discovery_urls_86.sqlite, las descarga y las convierte en texto limpio.

Esa es la razon de ser de Fase 3. El ETL anterior le mandaba a la IA el texto de
un dominio adivinado que casi nunca existia; aca se le manda el texto de paginas
que ya se sabe que responden y de que tipo son.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DISCOVERY = PROJECT_ROOT / "src" / "discovery"
if str(_DISCOVERY) not in sys.path:
    sys.path.insert(0, str(_DISCOVERY))

from validator import MAX_BYTES_HTML, _sesion  # noqa: E402

try:
    from .modelos import TipoFuente
except ImportError:
    from modelos import TipoFuente  # type: ignore[no-redef]

SQLITE_DISCOVERY = PROJECT_ROOT / "data" / "processed" / "discovery" / "discovery_urls_86.sqlite"

MAX_CHARS_POR_PAGINA = 4000
MAX_PAGINAS_POR_MUNICIPIO = 8
TIMEOUT = 20
WORKERS = 5

# Que tipos de URL sirven para leer texto. Las redes sociales y las stores
# devuelven muros de login, no contenido: se usan como senal, no como texto.
TIPOS_LEIBLES = (
    "sitio_oficial",
    "tramites",
    "transparencia",
    "salud_turnos",
    "hacienda_tasas_rafam",
    "reclamos_147",
    "gde_expediente",
    "licitaciones",
    "normativa_ordenanzas",
)

# Orden de lectura: primero lo que mas variables responde.
PRIORIDAD = {t: i for i, t in enumerate(TIPOS_LEIBLES)}

TIPO_A_FUENTE = {
    "facebook_oficial": TipoFuente.RED_SOCIAL,
    "instagram_oficial": TipoFuente.RED_SOCIAL,
    "youtube_oficial": TipoFuente.RED_SOCIAL,
    "play_store": TipoFuente.STORE_APP,
    "app_store": TipoFuente.STORE_APP,
    "boletin_sibom": TipoFuente.REGISTRO_PROVINCIAL,
}


class Pagina(NamedTuple):
    url: str
    tipo: str
    confianza_url: str  # la que le puso Fase 3
    texto: str

    @property
    def tipo_fuente(self) -> TipoFuente:
        return TIPO_A_FUENTE.get(self.tipo, TipoFuente.PORTAL_OFICIAL)


class URLCandidata(NamedTuple):
    url: str
    tipo: str
    confianza: str


def urls_de_municipio(
    municipio: str, sqlite_path: Path = SQLITE_DISCOVERY
) -> List[URLCandidata]:
    """URLs leibles del municipio, en orden de utilidad."""
    if not Path(sqlite_path).exists():
        raise FileNotFoundError(
            f"No existe {sqlite_path}. Corre Fase 3 primero: "
            "python src/discovery/discovery_engine.py --all"
        )
    con = sqlite3.connect(sqlite_path)
    try:
        filas = con.execute(
            "SELECT url, tipo, confianza FROM discovery_urls "
            "WHERE municipio = ? AND tipo IN (%s)" % ",".join("?" * len(TIPOS_LEIBLES)),
            (municipio, *TIPOS_LEIBLES),
        ).fetchall()
    finally:
        con.close()

    candidatas = [URLCandidata(*f) for f in filas]
    orden_confianza = {"Alta": 0, "Media": 1, "Baja": 2, "0%": 3}
    candidatas.sort(
        key=lambda c: (PRIORIDAD.get(c.tipo, 99), orden_confianza.get(c.confianza, 9))
    )

    # Una pagina por tipo alcanza: leer 4 notas de salud no agrega informacion
    # y gasta contexto que se le manda a la IA.
    vistos, unicas = set(), []
    for c in candidatas:
        if c.tipo in vistos:
            continue
        vistos.add(c.tipo)
        unicas.append(c)
    return unicas[:MAX_PAGINAS_POR_MUNICIPIO]


class URLTipificada(NamedTuple):
    url: str
    tipo: str
    confianza: str
    fragmento: Optional[str]


def todas_las_urls(
    municipio: str, sqlite_path: Path = SQLITE_DISCOVERY
) -> List[URLTipificada]:
    """Todas las URLs que Fase 3 le encontro al municipio, con su evidencia.

    Se usan para responder sin IA las variables que el tipo de URL ya prueba:
    si Fase 3 valido una URL de tipo licitaciones con su fragmento, entonces el
    municipio publica licitaciones. Preguntarselo a un modelo seria peor: la
    evidencia ya existe y es mas dura.
    """
    if not Path(sqlite_path).exists():
        return []
    con = sqlite3.connect(sqlite_path)
    try:
        filas = con.execute(
            "SELECT url, tipo, confianza, titulo_fragmento FROM discovery_urls "
            "WHERE municipio = ?",
            (municipio,),
        ).fetchall()
    finally:
        con.close()
    return [URLTipificada(*f) for f in filas]


def limpiar_html(html: str) -> str:
    """HTML -> texto plano legible, sin scripts, menus ni pies de pagina."""
    sopa = BeautifulSoup(html, "html.parser")
    for tag in sopa(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    texto = sopa.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", texto).strip()


def descargar(candidata: URLCandidata, timeout: int = TIMEOUT) -> Optional[Pagina]:
    import requests

    try:
        resp = _sesion().get(candidata.url, timeout=timeout, allow_redirects=True, stream=True)
        crudo = resp.raw.read(MAX_BYTES_HTML, decode_content=True) or b""
        resp.close()
        if resp.status_code >= 400:
            return None
        encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        texto = limpiar_html(crudo.decode(encoding, errors="replace"))
    except requests.RequestException:
        return None

    if len(texto) < 80:  # una pagina sin texto util no aporta evidencia
        return None
    return Pagina(
        url=candidata.url,
        tipo=candidata.tipo,
        confianza_url=candidata.confianza,
        texto=texto[:MAX_CHARS_POR_PAGINA],
    )


def leer_paginas(
    municipio: str,
    sqlite_path: Path = SQLITE_DISCOVERY,
    workers: int = WORKERS,
) -> List[Pagina]:
    """Descarga en paralelo las paginas leibles del municipio."""
    candidatas = urls_de_municipio(municipio, sqlite_path)
    if not candidatas:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(candidatas)))) as pool:
        paginas = list(pool.map(descargar, candidatas))
    return [p for p in paginas if p is not None]


__all__ = [
    "MAX_CHARS_POR_PAGINA",
    "MAX_PAGINAS_POR_MUNICIPIO",
    "Pagina",
    "URLCandidata",
    "descargar",
    "leer_paginas",
    "limpiar_html",
    "urls_de_municipio",
]
