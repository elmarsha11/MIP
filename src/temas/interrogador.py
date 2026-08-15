"""
Le pregunta al modelo por un tema y verifica lo que vuelve.

Misma regla que Fase 4 y que el motor comercial (ADR-0014): el modelo PROPONE y
el codigo COMPRUEBA. Aca comprobar son dos pasos:

1. **La cita existe literal** en alguna de las paginas que se le dieron.
2. **La cita sostiene lo que se afirma** — eso lo deciden los guards.

Lo que el modelo aporta y no se puede verificar es el `resumen`: la lectura en
prosa de que encontro. Por eso viaja siempre pegado a su cita, nunca solo.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
for _ruta in (_AQUI, _SRC / "extraction"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from modelos import cita_esta_en_fuente  # noqa: E402

from guardas import clasificar, conciliar  # noqa: E402
from rastreo import Estado, HallazgoTema, SubTema, Tema, TipoEvidencia  # noqa: E402

# Techo por sub-tema. No es una meta: si hay una sola accion, es una. Existe
# para que el modelo no rellene la lista con ruido.
MAX_POR_SUBTEMA = 4

# Cuanto texto de cada pagina entra al prompt. Igual que Fase 4.
MAX_CHARS_POR_PAGINA = 4000


def esquema_respuesta(tema: Tema) -> dict:
    return {
        "type": "object",
        "properties": {
            "hallazgos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subtema": {
                            "type": "string",
                            "enum": list(tema.ids_subtemas),
                        },
                        "resumen": {
                            "type": "string",
                            "description": (
                                "Que encontraste, en una o dos frases y sin jerga. "
                                "Si la cita muestra que lo hace otro organismo, "
                                "decilo."
                            ),
                        },
                        "cita_literal": {
                            "type": "string",
                            "description": (
                                "Fragmento copiado EXACTAMENTE del texto, palabra "
                                "por palabra. Si no podes copiar uno, no inventes "
                                "el hallazgo."
                            ),
                        },
                        "pagina": {"type": "integer"},
                    },
                    "required": ["subtema", "resumen", "cita_literal", "pagina"],
                },
            }
        },
        "required": ["hallazgos"],
    }


def _bloque_subtemas(tema: Tema) -> str:
    lineas = []
    for i, s in enumerate(tema.subtemas, 1):
        lineas.append(f"{i}. [{s.id}] {s.pregunta}")
        lineas.append(f"   Que tiene que probar la cita: {s.que_prueba}")
    return "\n".join(lineas)


def _bloque_paginas(paginas: Sequence) -> str:
    partes = []
    for i, p in enumerate(paginas, 1):
        texto = (getattr(p, "texto", "") or "")[:MAX_CHARS_POR_PAGINA]
        partes.append(f"--- PAGINA {i} ({getattr(p, 'url', '')}) ---\n{texto}")
    return "\n\n".join(partes)


def construir_prompt(municipio: str, tema: Tema, paginas: Sequence) -> str:
    return f"""Sos un analista que lee documentacion municipal argentina y responde SOLO con lo que el texto dice.

MUNICIPIO: {municipio}
TEMA: {tema.nombre}

Preguntas a responder:
{_bloque_subtemas(tema)}

REGLAS, en orden de importancia:
1. Cada hallazgo necesita una cita copiada LITERAL del texto, palabra por palabra.
   Si tenes que parafrasear para que se entienda, no sirve: copiala igual.
2. Si el texto no responde una pregunta, no devuelvas nada para esa pregunta.
   No hay premio por completar la lista. El vacio es una respuesta valida.
3. No infieras desde la ausencia. Que el texto no mencione algo no prueba que no exista.
4. Si el texto muestra que lo hace otro organismo y no el municipio, igual devolve
   el hallazgo con esa cita: sirve saber que no le compete al municipio.
5. Maximo {MAX_POR_SUBTEMA} hallazgos por pregunta. Preferí uno solido antes que cuatro flojos.

TEXTO DE LAS PAGINAS:
{_bloque_paginas(paginas)}
"""


def verificar_respuesta(
    respuesta: Optional[dict],
    municipio: str,
    id_municipio: str,
    tema: Tema,
    paginas: Sequence,
    fecha: str,
    modelo: Optional[str] = None,
) -> List[HallazgoTema]:
    """Convierte lo que devolvio el modelo en hallazgos verificados.

    Descarta en silencio lo que no pasa: un hallazgo sin cita literal en el
    texto no es un error del sistema, es el sistema funcionando.
    """
    if not respuesta:
        return []

    crudos = respuesta.get("hallazgos") or []
    if not isinstance(crudos, list):
        return []

    por_subtema: Dict[str, int] = {}
    verificados: List[HallazgoTema] = []

    for crudo in crudos:
        if not isinstance(crudo, dict):
            continue

        subtema: Optional[SubTema] = tema.subtema(str(crudo.get("subtema") or ""))
        if subtema is None:
            continue

        cita = str(crudo.get("cita_literal") or "").strip()
        if not cita:
            continue

        # Paso 1: la cita tiene que existir literal en alguna pagina que se le
        # mostro. Se prueba contra todas y no solo contra la que dijo el modelo,
        # porque el indice de pagina es lo primero que alucina.
        pagina = next(
            (p for p in paginas if cita_esta_en_fuente(cita, getattr(p, "texto", ""))),
            None,
        )
        if pagina is None:
            continue

        # Paso 2: que sostiene esa cita.
        tipo = _tipo_de(pagina)
        estado = conciliar(crudo.get("estado"), clasificar(cita, subtema, tipo))
        if estado is Estado.SIN_EVIDENCIA:
            continue

        cupo = por_subtema.get(subtema.id, 0)
        if cupo >= MAX_POR_SUBTEMA:
            continue
        por_subtema[subtema.id] = cupo + 1

        verificados.append(
            HallazgoTema(
                municipio=municipio,
                id_municipio=id_municipio,
                tema=tema.id,
                subtema=subtema.id,
                estado=estado,
                resumen=str(crudo.get("resumen") or "").strip(),
                cita=cita,
                url=getattr(pagina, "url", ""),
                tipo_evidencia=tipo,
                fecha=fecha,
                modelo=modelo,
            )
        )

    return verificados


def _tipo_de(pagina) -> TipoEvidencia:
    """De que clase de fuente salio esta pagina."""
    explicito = getattr(pagina, "tipo_evidencia", None)
    if isinstance(explicito, TipoEvidencia):
        return explicito
    if isinstance(explicito, str):
        try:
            return TipoEvidencia(explicito)
        except ValueError:
            pass

    tipo = (getattr(pagina, "tipo", "") or "").lower()
    if tipo in ("prensa", "medio", "nota"):
        return TipoEvidencia.PRENSA
    if tipo in ("boletin_sibom", "normativa_ordenanzas", "boletin", "normativa"):
        return TipoEvidencia.NORMATIVA
    return TipoEvidencia.OFICIAL


__all__ = [
    "MAX_POR_SUBTEMA",
    "construir_prompt",
    "esquema_respuesta",
    "verificar_respuesta",
]
