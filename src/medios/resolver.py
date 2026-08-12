"""
De nombre de medio a URL: "El Fuerte Diario" -> https://elfuertediario.com.ar

La semilla trae NOMBRES, no direcciones. Sin URL no se puede leer nada, asi que
este paso es el puente entre lo que Juli releva a mano y lo que el codigo puede
consumir.

**No usa buscadores.** Es la leccion de la Capa 2 de Fase 3, que esta en el
handoff: los buscadores publicos bloquean por volumen y no escalan. Lo que si
escala son los patrones de dominio con validacion por titulo, que resolvieron 85
de 86 sitios municipales.

La validacion es lo que hace que esto no invente: un dominio que responde no
alcanza, el TITULO de la pagina tiene que parecerse al nombre del medio. Sin eso
se cae en dominios parkeados, que responden 200 con publicidad para cualquier
nombre que uno pruebe.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from typing import List, NamedTuple, Optional

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
for _ruta in (_AQUI, PROJECT_ROOT / "src" / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

TIMEOUT = 20

# Sufijos en orden de probabilidad para un medio argentino.
SUFIJOS = (".com.ar", ".com", ".ar", ".net.ar", ".org.ar")

# Palabras que no aportan al dominio: casi ningun medio las pone en la URL.
# "El Fuerte Diario" -> elfuerte / elfuertediario, no "eldiariofuerte".
RUIDO = (
    "diario", "el", "la", "los", "las", "de", "del", "noticias", "portal",
    "periodico", "semanario", "radio", "fm", "am", "digital", "online",
    "web", "info", "news", "tv",
)


class MedioResuelto(NamedTuple):
    nombre: str
    url: Optional[str]
    titulo: Optional[str]
    motivo: str


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _palabras(nombre: str) -> List[str]:
    limpio = _sin_tildes(nombre)
    # Se corta en el guion: "La Región Web - Guaminí" es el mismo medio que
    # "La Región Web" cubriendo otro partido, y el dominio es el del medio.
    limpio = limpio.split(" - ")[0]
    return [p for p in re.split(r"[^a-z0-9]+", limpio) if p]


def candidatos(nombre: str) -> List[str]:
    """Dominios plausibles para ese nombre, del mas probable al menos.

    Se generan varias formas porque no hay una regla: "InfoSalto" es
    infosalto.com.ar y "El Fuerte Diario" es elfuertediario.com.ar, pero
    "La Voz del Pueblo" es lavozdelpueblo.com.ar y no "lavoz".
    """
    palabras = _palabras(nombre)
    if not palabras:
        return []

    completo = "".join(palabras)
    sin_ruido = "".join(p for p in palabras if p not in RUIDO) or completo
    # Con articulo pero sin la palabra generica final ("diario", "noticias").
    sin_generico = "".join(p for p in palabras if p not in RUIDO[0:1] + RUIDO[6:])

    bases = []
    for b in (completo, sin_generico, sin_ruido):
        if b and b not in bases and len(b) >= 4:
            bases.append(b)

    # https primero y http despues, por dominio: un medio chico puede no tener
    # TLS y eso NO lo descalifica. Es ADR-0012, que el proyecto ya establecio
    # para los portales municipales y que este modulo estaba ignorando:
    # bolivarhoy.com.ar existe y responde solo por http, asi que quedaba como
    # "ningun dominio candidato responde" teniendo sitio.
    urls = []
    for b in bases:
        for s in SUFIJOS:
            urls.append(f"https://{b}{s}")
            urls.append(f"http://{b}{s}")
    return urls


def _parecido(titulo: str, nombre: str) -> bool:
    """El titulo tiene que compartir la parte distintiva del nombre.

    Se comparan las palabras SIN ruido: casi todo medio se llama "Diario X" o
    "X Noticias", asi que coincidir en "diario" no prueba nada. Lo que tiene que
    coincidir es la X.
    """
    distintivas = {p for p in _palabras(nombre) if p not in RUIDO and len(p) > 3}
    if not distintivas:
        distintivas = {p for p in _palabras(nombre) if len(p) > 3}
    if not distintivas:
        return False
    del_titulo = set(re.split(r"[^a-z0-9]+", _sin_tildes(titulo)))
    return bool(distintivas & del_titulo)


def resolver(nombre: str, timeout: int = TIMEOUT) -> MedioResuelto:
    """Primera URL que responde Y cuyo titulo se parece al nombre del medio.

    `consultar` devuelve un RespuestaHTTP(status, url_final, titulo, error) y ya
    extrae el titulo: no hay que volver a parsear el HTML.
    """
    from validator import consultar

    probados = 0
    for url in candidatos(nombre):
        respuesta = consultar(url, timeout=timeout)
        if respuesta.status is None or respuesta.status >= 400:
            continue
        probados += 1
        # Se guarda url_final, no la candidata: muchos medios redirigen de .com
        # a .com.ar o a un subdominio, y la que sirve para leer es la de destino.
        if respuesta.titulo and _parecido(respuesta.titulo, nombre):
            return MedioResuelto(nombre, respuesta.url_final, respuesta.titulo, "titulo coincide")

    if probados:
        # Respondio algo pero ningun titulo coincidio. Es el caso del dominio
        # parkeado: aceptarlo seria darle a un municipio un medio que no existe.
        return MedioResuelto(nombre, None, None, "responde pero el titulo no coincide")
    return MedioResuelto(nombre, None, None, "ningun dominio candidato responde")


__all__ = ["MedioResuelto", "RUIDO", "SUFIJOS", "candidatos", "resolver"]
