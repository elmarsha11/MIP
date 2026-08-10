"""
Verificacion de que un nombre sea una PERSONA EN EL CARGO y no un edificio.

Por que existe: en el texto de los portales municipales, "Intendente" aparece
tanto en "el Intendente Municipal, Javier Osuna" como en "Centro de Salud
«Intendente Pedro Carossi»". Lo segundo es un CAPS bautizado con el nombre de un
intendente anterior, a veces muerto hace decadas.

Las dos citas son literales y las dos pasan la verificacion de ADR-0014. La
diferencia esta en el contexto, no en la cita. Este modulo mira el contexto.

Es el mismo agujero que ya mordio dos veces en este proyecto:
  - Fase 4: con la cita real "obras de bacheo en el barrio Belgrano", el valor
    "Juan Perez" entraba como intendente verificado.
  - Motor comercial: la cita "registrate en el siguiente link" entraba como
    oportunidad, siendo que probaba lo contrario.

Genera falsos negativos y esta bien: un intendente de menos se completa a mano,
un intendente equivocado se lleva puesta la credibilidad de la base entera.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Palabras que, delante de un nombre, delatan que el nombre bautiza una COSA y no
# nombra a quien ejerce el cargo.
_COSAS = (
    "centro", "centro de salud", "caps", "unidad sanitaria", "hospital",
    "escuela", "jardin", "instituto", "colegio", "universidad",
    "calle", "avenida", "av", "diagonal", "pasaje", "ruta", "camino",
    "plaza", "parque", "paseo", "plazoleta", "predio", "playon",
    "barrio", "villa", "complejo", "polideportivo", "estadio", "club",
    "biblioteca", "museo", "teatro", "anfiteatro", "salon", "sala",
    "puente", "monumento", "busto", "cementerio", "delegacion",
    "aeroclub", "balneario", "camping", "terminal", "estacion",
)

# Cuanto texto hacia atras se mira. Suficiente para agarrar "Centro de Salud
# «...»" y corto para no traerse una frase entera de otro tema.
_VENTANA = 46

_COMILLAS_ABRE = "\"'«“‘"
_COMILLAS_CIERRA = "\"'»”’"


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", _sin_tildes(texto)).strip()


# Titulos que se intercalan entre la cosa y el nombre al bautizar: "Centro de
# Salud Intendente Pedro Carossi", "Escuela Doctor Rene Favaloro". Sin
# contemplarlos, la palabra-cosa deja de estar pegada al nombre y el filtro no
# engancha, que es como se colaba el caso mas comun de todos.
_TITULOS = (
    "intendente", "dr", "dra", "doctor", "doctora", "profesor", "profesora",
    "prof", "maestro", "maestra", "general", "coronel", "sargento", "comandante",
    "presidente", "gobernador", "ingeniero", "ing", "arquitecto", "padre",
    "monsenor", "san", "santa", "santo", "madre", "don", "dona",
)

_RE_COSAS = re.compile(
    r"(?:" + "|".join(re.escape(c) for c in _COSAS) + r")\W+"
    r"(?:(?:" + "|".join(re.escape(t) for t in _TITULOS) + r")\W+)*$",
    re.IGNORECASE,
)


def _entre_comillas(cita: str, inicio: int, fin: int) -> bool:
    """True si el nombre esta encomillado.

    Encomillar es como se bautiza: Centro de Salud "Intendente Pedro Carossi".
    Un secretario en ejercicio no aparece entre comillas en una nota.
    """
    antes = cita[max(0, inicio - _VENTANA):inicio]
    despues = cita[fin:fin + _VENTANA]
    abre = any(c in antes for c in _COMILLAS_ABRE)
    cierra = any(c in despues for c in _COMILLAS_CIERRA)
    return abre and cierra


def nombre_valido_en_cita(nombre: str, cita: str) -> bool:
    """El nombre esta en la cita Y nombra a una persona en ejercicio.

    Tres condiciones, todas necesarias:
      1. el nombre aparece literal en la cita (ADR-0014, valor dentro de la cita)
      2. no viene precedido de una palabra que bautiza cosas
      3. no esta entre comillas
    """
    n, c = _normalizar(nombre), _normalizar(cita)
    if len(n) < 5 or " " not in n:
        return False  # un apellido suelto no identifica a nadie
    if n not in c:
        return False

    # Todas las apariciones tienen que ser sospechosas para descartar: si el
    # nombre figura una vez como calle y otra como firmante, vale.
    for m in re.finditer(re.escape(n), c):
        antes = c[max(0, m.start() - _VENTANA):m.start()]
        if _RE_COSAS.search(antes):
            continue
        if _entre_comillas(c, m.start(), m.end()):
            continue
        return True
    return False


def motivo_del_rechazo(nombre: str, cita: str) -> Optional[str]:
    """Por que se rechazo. Para que la cola de revision sea legible."""
    n, c = _normalizar(nombre), _normalizar(cita)
    if len(n) < 5 or " " not in n:
        return "nombre incompleto"
    if n not in c:
        return "el nombre no esta en la cita"
    if nombre_valido_en_cita(nombre, cita):
        return None
    for m in re.finditer(re.escape(n), c):
        if _RE_COSAS.search(c[max(0, m.start() - _VENTANA):m.start()]):
            return "el nombre bautiza un lugar, no nombra al funcionario"
    return "el nombre esta entrecomillado, parece un nombre propio de lugar"


__all__ = ["motivo_del_rechazo", "nombre_valido_en_cita"]
