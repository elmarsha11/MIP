"""
Que tiene y como opera cada municipio en seguridad, segun su prensa local.

Es el segundo eje. El SNIC dice CUANTO delito se denuncia; esto dice QUE HACE el
municipio: si tiene patrulla urbana propia, si hay centro de monitoreo, que
fuerzas actuan en el territorio, si se hacen allanamientos y operativos.

La regla de siempre (ADR-0014) con los guards que el proyecto fue aprendiendo:

  1. la cita existe LITERAL en la nota
  2. la cita nombra el ASPECTO que se afirma          <- gabinete, Tornquist
  3. la nota es de ESTE municipio                     <- prensa.py

El paso 2 es el que no se puede saltear. Una nota que dice "el intendente hablo
de seguridad" menciona el tema y no prueba nada; "se inauguro el centro de
monitoreo con 40 camaras" prueba. Es la misma familia de agujero que dejo entrar
"Sergio F. Bordoni" como intendente de Tornquist.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
for _ruta in (_AQUI, _SRC / "extraction"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from modelos import cita_esta_en_fuente  # noqa: E402  (src/extraction/modelos.py)

from prensa import CONSULTAS  # noqa: E402

# Cuantas notas se le mandan al modelo por aspecto. Un medio puede tener 200
# notas locales en 12 meses; mandarlas todas es medio millon de caracteres para
# responder siete preguntas de si o no. Las mas recientes alcanzan y ademas son
# las que describen el estado ACTUAL, que es lo que se pregunta.
NOTAS_POR_ASPECTO = 3
MAX_CHARS_NOTA = 900

# Lo que la cita tiene que nombrar para probar cada aspecto. Sin esto entra
# cualquier nota que hable de seguridad en general.
PRUEBA_DEL_ASPECTO: Dict[str, tuple] = {
    "patrulla_urbana": (r"patrulla", r"polic[ií]a local", r"guardia urbana", r"prevenci[oó]n"),
    "centro_monitoreo": (r"monitoreo", r"c[aá]mara", r"videovigilancia", r"lector[a]? de patente"),
    "policia_bonaerense": (r"bonaerense", r"comisar[ií]a", r"destacamento", r"polic[ií]a de la provincia"),
    "fuerzas_federales": (r"gendarmer[ií]a", r"polic[ií]a federal", r"prefectura", r"fuerzas federales"),
    "allanamientos": (r"allanamiento", r"orden de allanamiento"),
    "operativos": (r"operativo", r"control vehicular", r"saturaci[oó]n"),
    "alarmas_vecinales": (r"alarma", r"bot[oó]n antip[aá]nico", r"antip[aá]nico"),
}

_RE_PRUEBA = {a: re.compile("|".join(p), re.IGNORECASE) for a, p in PRUEBA_DEL_ASPECTO.items()}

ESQUEMA_RESPUESTA = {
    "type": "object",
    "properties": {
        "aspectos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "aspecto": {"type": "string", "enum": list(CONSULTAS)},
                    "presente": {"type": "string", "enum": ["si", "no_verificable"]},
                    "detalle": {
                        "type": "string",
                        "description": (
                            "Que hay o que paso, en una frase, en la lengua de un "
                            "intendente y no de un sistema."
                        ),
                    },
                    "cita_literal": {
                        "type": "string",
                        "description": (
                            "Fragmento copiado EXACTAMENTE de una nota, que PRUEBE "
                            "el aspecto. Palabra por palabra."
                        ),
                    },
                },
                "required": ["aspecto", "presente", "detalle", "cita_literal"],
            },
        }
    },
    "required": ["aspectos"],
}


def armar_texto(notas: Sequence) -> Tuple[str, Dict[str, object]]:
    """Las notas mas recientes por aspecto, numeradas, y el indice para volver."""
    por_aspecto: Dict[str, list] = {}
    for n in sorted(notas, key=lambda x: x.fecha, reverse=True):
        elegidas = por_aspecto.setdefault(n.aspecto, [])
        if len(elegidas) < NOTAS_POR_ASPECTO and all(e.url != n.url for e in elegidas):
            elegidas.append(n)

    bloques, indice = [], {}
    i = 0
    for aspecto, elegidas in por_aspecto.items():
        for n in elegidas:
            i += 1
            indice[str(i)] = n
            bloques.append(
                f"--- NOTA {i} | aspecto: {aspecto} | {n.fecha} | {n.medio}\n"
                f"{n.titulo}\n{n.texto[:MAX_CHARS_NOTA]}"
            )
    return "\n\n".join(bloques), indice


def construir_prompt(municipio: str, texto: str) -> str:
    aspectos = "\n".join(f"- {a}: {', '.join(t)}" for a, t in CONSULTAS.items())
    return f"""Sos un analista de seguridad municipal. Lee las notas de la prensa
local de {municipio} de los ultimos 12 meses y reporta QUE TIENE y COMO OPERA el
municipio en seguridad.

NO te interesa cuanto delito hay: eso ya lo da la estadistica oficial. Lo que hay
que responder es que recursos existen y quien interviene.

ASPECTOS A REPORTAR, uno por cada uno:
{aspectos}

REGLAS:
1. Cada aspecto necesita una CITA COPIADA LITERAL de una nota, palabra por
   palabra. Se verifica automaticamente: si no coincide exacto, se descarta.
2. La cita tiene que PROBAR el aspecto, no solo mencionar el tema. "El intendente
   hablo de seguridad" no prueba que haya centro de monitoreo; "se inauguro el
   centro de monitoreo con 40 camaras" si.
3. Si las notas no alcanzan para afirmarlo, responde "no_verificable" con cita
   vacia. Es una respuesta CORRECTA y esperada, no un fracaso.
4. No infieras. Que exista una comisaria no significa que haya patrulla urbana
   municipal: son cosas distintas y las paga gente distinta.
5. En "detalle" poné lo concreto: cuantas camaras, que fuerza, que se secuestro.

NOTAS DE LA PRENSA LOCAL DE {municipio.upper()}:

{texto}
"""


def cita_prueba_aspecto(cita: str, aspecto: str) -> bool:
    """La cita nombra lo que se afirma.

    Es el guard que en el gabinete evito que "Sergio F. Bordoni" —un nombre
    suelto en una pagina— entrara como intendente. Aca evita que una nota que
    habla de seguridad en general pruebe que el municipio tiene camaras.
    """
    regla = _RE_PRUEBA.get(aspecto)
    return bool(regla and cita and regla.search(cita))


def verificar_respuesta(
    respuesta: Optional[dict],
    municipio: str,
    id_municipio: str,
    indice: Dict[str, object],
    fecha: str,
) -> Tuple[List[dict], int]:
    """Devuelve (aspectos verificados, cuantos se rechazaron)."""
    modelo = (respuesta or {}).get("_modelo")
    notas = list(indice.values())
    verificados: List[dict] = []
    rechazados = 0
    vistos = set()

    for item in (respuesta or {}).get("aspectos", []) or []:
        aspecto = (item.get("aspecto") or "").strip()
        if aspecto not in CONSULTAS or aspecto in vistos:
            continue
        if (item.get("presente") or "") != "si":
            continue

        cita = " ".join((item.get("cita_literal") or "").split())
        detalle = " ".join((item.get("detalle") or "").split())
        if not cita or not detalle:
            rechazados += 1
            continue

        nota = next((n for n in notas if cita_esta_en_fuente(cita, f"{n.titulo} {n.texto}")), None)
        if nota is None:
            rechazados += 1  # cita inventada o parafraseada
            continue

        if not cita_prueba_aspecto(cita, aspecto):
            rechazados += 1  # la cita existe pero no prueba lo que se afirma
            continue

        vistos.add(aspecto)
        verificados.append({
            "municipio": municipio,
            "id_municipio": id_municipio,
            "aspecto": aspecto,
            "detalle": detalle[:300],
            "cita": cita[:500],
            "medio": nota.medio,
            "url": nota.url,
            "fecha_nota": nota.fecha,
            "fecha": fecha,
            "modelo": modelo,
        })

    return verificados, rechazados


def leer(municipio: str, id_municipio: str, notas: Sequence, cliente, fecha: str) -> Tuple[List[dict], int]:
    if not notas or cliente is None:
        return [], 0
    texto, indice = armar_texto(notas)
    if not texto.strip():
        return [], 0
    respuesta = cliente.generar_json(construir_prompt(municipio, texto), ESQUEMA_RESPUESTA)
    return verificar_respuesta(respuesta, municipio, id_municipio, indice, fecha)


__all__ = [
    "ESQUEMA_RESPUESTA", "NOTAS_POR_ASPECTO", "PRUEBA_DEL_ASPECTO",
    "armar_texto", "cita_prueba_aspecto", "construir_prompt", "leer",
    "verificar_respuesta",
]
