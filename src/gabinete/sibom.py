"""
Acceso al Boletin Oficial Municipal (SIBOM) de la Provincia de Buenos Aires.

Es la fuente mas dura que existe para la cupula municipal: un decreto publicado,
con fecha, que nombra al secretario que lo refrenda. Mejor que cualquier resumen
de buscador y mejor que el propio portal del municipio.

Lo que se midio el 2026-08-09 antes de escribir esto:

  - **65 de los 86 municipios publican boletines.** Los otros 21 estan
    registrados en SIBOM pero no publicaron nunca (Navarro y Ayacucho, por
    ejemplo). Para esos hay que ir por otra fuente: no se inventa.
  - **Los PDF son texto extraible**, no escaneos. El boletin 117 de Chascomus
    son 105 paginas y 320.000 caracteres legibles.
  - **El formato NO es uniforme.** Chascomus firma con "El presente Decreto sera
    refrendado por el Secretario de Obras (Lucas Funes)"; Castelli publica
    146.000 caracteres sin usar esa formula. Por eso la lectura la hace un modelo
    y no una expresion regular, y por eso el codigo despues verifica la cita.

La paginacion no se recorre: interesa el gabinete de HOY, y para eso alcanzan los
boletines mas recientes, que estan en la primera pagina.
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional

import requests

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
PROJECT_ROOT = _SRC.parent
for _ruta in (_SRC / "discovery",):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "gabinete" / "cache"
BASE = "https://sibom.slyt.gba.gob.ar"
TIMEOUT = 90
CABECERAS = {"User-Agent": "MIP-relevamiento-municipal/0.1"}

# Cuantos boletines se leen por municipio.
#
# Empezo en 2 con el razonamiento de que un secretario firma todos los meses. Es
# falso para las carteras que firman poco: con 2 boletines Chascomus daba 7 de 8
# secretarias, y la que faltaba (Modernizacion) aparecio recien en el sexto.
#
# Subirlo es seguro desde que existe `fecha_norma`: un decreto viejo ya no puede
# pisar a uno nuevo, solo llenar huecos. El costo es de descarga, y se paga una
# sola vez porque el texto queda cacheado.
BOLETINES_POR_MUNICIPIO = 6

# INDEC/SIBOM y el Gold Standard no siempre escriben igual el nombre del partido.
# Mapeo explicito, nunca fuzzy: asignarle a un municipio el gabinete de otro es
# el peor error posible en este modulo.
ALIAS_SIBOM = {
    "generalmadariaga": "generaljuanmadariaga",
    "veinticincodemayo": "25demayo",
    "alem": "leandronalem",
    "coronelrosales": "coroneldemarinaleonardorosales",
    "gonzaleschaves": "adolfogonzaleschaves",
    "sanmigueldelmonte": "monte",
}


class Boletin(NamedTuple):
    municipio: str
    id_boletin: str
    url: str
    texto: str


def _sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update(CABECERAS)
    return s


def url_del_municipio(municipio: str) -> Optional[str]:
    """URL de la ficha del municipio en SIBOM, o None si no esta."""
    from registries import cargar_indice_sibom
    from schemas import normalizar_slug

    indice = cargar_indice_sibom()
    slug = normalizar_slug(municipio)
    return indice.get(slug) or indice.get(ALIAS_SIBOM.get(slug, ""))


def ids_de_boletines(url_municipio: str, sesion=None) -> List[str]:
    """IDs de los boletines mas recientes.

    En SIBOM los boletines no se enlazan con <a>: cada uno es un <form> que hace
    GET a /bulletins/<id>. Por eso se busca el patron en el HTML crudo y no se
    recorren anclas, que devuelven cero.
    """
    ses = sesion or _sesion()
    try:
        r = ses.get(url_municipio, timeout=TIMEOUT)
    except requests.RequestException:
        return []
    if r.status_code != 200:
        return []
    # dict.fromkeys preserva el orden de aparicion: SIBOM lista del mas nuevo al
    # mas viejo, y el gabinete de hoy esta en el mas nuevo.
    return list(dict.fromkeys(re.findall(r"/bulletins/(\d+)", r.text)))


def _path_cache(id_boletin: str) -> Path:
    return CACHE_DIR / f"boletin_{id_boletin}.json"


def texto_del_boletin(id_boletin: str, sesion=None) -> Optional[str]:
    """Texto plano del PDF del boletin, del cache si esta.

    Devuelve None si no se pudo bajar o si el PDF no tiene texto (un boletin
    escaneado es ilegible para MIP, y eso es un dato: no se rellena con nada).

    **Solo se cachean los aciertos.** Guardar un None convertiria un corte de red
    en un "este municipio no publica" permanente. Ya paso tres veces en este
    proyecto.
    """
    cache = _path_cache(id_boletin)
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))["texto"]
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    ses = sesion or _sesion()
    try:
        r = ses.get(f"{BASE}/bulletins/{id_boletin}.pdf", timeout=TIMEOUT * 2)
    except requests.RequestException:
        return None
    if r.status_code != 200 or "pdf" not in (r.headers.get("content-type") or ""):
        return None

    try:
        from pypdf import PdfReader

        lector = PdfReader(io.BytesIO(r.content))
        texto = " ".join(
            " ".join((p.extract_text() or "").split()) for p in lector.pages
        ).strip()
    except Exception:
        return None

    if len(texto) < 500:
        return None  # escaneado o vacio: no hay evidencia que leer

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps({"id": id_boletin, "texto": texto}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass
    return texto


def boletines(municipio: str, maximo: int = BOLETINES_POR_MUNICIPIO) -> List[Boletin]:
    """Los boletines mas recientes del municipio, con su texto."""
    url = url_del_municipio(municipio)
    if not url:
        return []

    ses = _sesion()
    salida: List[Boletin] = []
    for id_boletin in ids_de_boletines(url, ses)[:maximo]:
        texto = texto_del_boletin(id_boletin, ses)
        if texto:
            salida.append(
                Boletin(
                    municipio=municipio,
                    id_boletin=id_boletin,
                    url=f"{BASE}/bulletins/{id_boletin}",
                    texto=texto,
                )
            )
    return salida


__all__ = ["BASE", "Boletin", "boletines", "ids_de_boletines", "texto_del_boletin",
           "url_del_municipio"]
