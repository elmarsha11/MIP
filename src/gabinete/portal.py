"""
Segunda fuente: el texto del portal oficial del municipio.

Para que existe: 21 de los 86 no publican boletines en SIBOM, y aun entre los que
publican, el intendente casi nunca firma con su nombre — en Chascomus "Gaston"
aparece una sola vez en 773.000 caracteres, y encima referido a otra persona.

En el portal pasa lo contrario: el intendente esta en cada nota de prensa. Medido
el 2026-08-09 sobre el texto ya cacheado: **48 de 84 municipios** lo nombran.

Es una fuente mas blanda que el decreto y por eso entra con confianza Media: una
nota puede ser vieja y no siempre esta fechada. Sirve para llenar huecos y para
CONTRASTAR, que es su otro trabajo. Cuando el portal y el boletin nombran a
personas distintas para el mismo cargo, eso no se resuelve eligiendo: se muestra.

No descarga nada nuevo: reusa el cache de paginas que armo el motor comercial.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
for _ruta in (_SRC / "oportunidades", _SRC / "extraction", _SRC / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))


def paginas_del_portal(municipio: str, id_municipio: str) -> List:
    """Paginas del portal oficial, del cache si estan.

    Devuelve objetos con .texto y .url, que es lo que espera `lector.leer`.
    """
    from paginas import obtener_paginas  # src/oportunidades/paginas.py

    try:
        return obtener_paginas(municipio, id_municipio, usar_cache=True)
    except Exception:
        # Un portal caido no puede tumbar la corrida de los 86: el municipio
        # queda sin dato de portal, que es una respuesta valida.
        return []


__all__ = ["paginas_del_portal"]
