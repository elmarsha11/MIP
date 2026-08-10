"""
Cache del texto de las paginas ya descargadas.

Fase 4 vuelve a descargar todo en cada corrida. Para Fase 4 esta bien: quiere el
portal como esta hoy. Aca no: la lectura comercial se va a re-correr muchas veces
mientras se afina el prompt, y volver a crawlear 86 portales en cada iteracion es
lento y ademas es maltratar servidores municipales.

**Solo se cachean los aciertos.** Un municipio del que no se pudo bajar nada NO
se guarda. Es la trampa que ya costo tiempo tres veces en este proyecto: guardar
un None convierte un fallo de red en un "no existe" permanente.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
PROJECT_ROOT = _SRC.parent
for _ruta in (_SRC / "extraction", _SRC / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from fetcher import (  # noqa: E402
    SQLITE_DISCOVERY,
    Pagina,
    leer_paginas,
    paginas_de_turnos,
)

CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "oportunidades" / "cache"


def _path(id_municipio: str) -> Path:
    return CACHE_DIR / f"paginas_{id_municipio}.json"


def _leer_cache(id_municipio: str) -> List[Pagina]:
    path = _path(id_municipio)
    if not path.exists():
        return []
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        Pagina(
            url=d["url"],
            tipo=d["tipo"],
            confianza_url=d["confianza_url"],
            texto=d["texto"],
        )
        for d in datos
    ]


def _escribir_cache(id_municipio: str, paginas: List[Pagina]) -> None:
    if not paginas:
        return  # regla: no se cachea el vacio
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _path(id_municipio).write_text(
            json.dumps(
                [
                    {
                        "url": p.url,
                        "tipo": p.tipo,
                        "confianza_url": p.confianza_url,
                        "texto": p.texto,
                    }
                    for p in paginas
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def obtener_paginas(
    municipio: str,
    id_municipio: str,
    usar_cache: bool = True,
    sqlite_discovery: Path = SQLITE_DISCOVERY,
) -> List[Pagina]:
    """Texto de las paginas del municipio, del cache si esta."""
    if usar_cache:
        cacheadas = _leer_cache(id_municipio)
        if cacheadas:
            return cacheadas

    paginas = leer_paginas(municipio, sqlite_discovery)
    # Misma cosecha dirigida que Fase 4: los procesos de turnos no estan en la
    # home sino un nivel adentro.
    ya = {p.url for p in paginas}
    paginas += [
        p for p in paginas_de_turnos(municipio, sqlite_discovery) if p.url not in ya
    ]

    if usar_cache:
        _escribir_cache(id_municipio, paginas)
    return paginas


__all__ = ["CACHE_DIR", "obtener_paginas"]
