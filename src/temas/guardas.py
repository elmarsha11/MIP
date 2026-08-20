"""
Los guards: que puede afirmarse a partir de una cita.

El modelo PROPONE, el codigo COMPRUEBA (ADR-0014). En Fase 4 comprobar era una
sola cosa: que la cita exista literal. Aca hay tres reglas mas, y cada una nacio
de un modo concreto de equivocarse:

1. **La prensa no confirma politica.** Una nota sobre una jornada de reciclaje
   prueba que hubo una jornada, no que el municipio tenga un programa. Si se
   mezclan, el ranking lo encabeza el municipio con mejor prensa, no el que mas
   hace.

2. **La cita puede probar que el tema es de otro.** Por Ley 11.459 el
   Certificado de Aptitud Ambiental de una industria de tercera categoria lo
   emite OPDS. Un portal municipal que explica ese tramite provincial esta
   diciendo lo contrario de "el municipio fiscaliza". Sin este guard, la pagina
   que mejor prueba que NO compete se leeria como que si.

3. **Un anuncio no es un hecho.** "Se construira una planta de reciclado" no es
   una accion ambiental en curso.

Los tres generan falsos negativos y esta bien: una lista corta y confiable vale
mas que una larga que hay que auditar. Cuando el modelo y el codigo discrepan,
gana el mas conservador.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
for _ruta in (_AQUI, _SRC / "extraction"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from modelos import normalizar_para_cotejo  # noqa: E402

from rastreo import Estado, SubTema, TipoEvidencia  # noqa: E402

# Una cita mas corta que esto no prueba nada: cualquier texto contiene
# "ambiente". Mismo umbral que usa cita_esta_en_fuente en Fase 4.
MINIMO_CITA = 12

# Marcas de que el sujeto de la frase es el municipio. Sin alguna de estas, una
# cita que nombra un organismo provincial no puede leerse como accion municipal.
MARCAS_MUNICIPALES = (
    "municipio",
    "municipal",
    "municipalidad",
    "la comuna",
    "el ejecutivo",
    "intendente",
    "intendencia",
    "secretaria de",
    "direccion de",
    "subsecretaria de",
    "ordenanza",
    "concejo deliberante",
    "hcd",
)

# Verbos y giros que ponen la accion en el futuro o en el deseo.
MARCAS_FUTURO = (
    "se construira",
    "se instalara",
    "se implementara",
    "se lanzara",
    "sera inaugurad",
    "sera construid",
    "proximamente",
    "en los proximos",
    "esta previsto",
    "se preve",
    "se proyecta",
    "proyecta construir",
    "tiene previsto",
    "planea",
    "va a construir",
    "va a implementar",
    "licitara",
)

# Giros que prueban que la cosa ya existe. Ganan sobre las marcas de futuro:
# "la planta que se construira en 2020 ya funciona" es un hecho, no un anuncio.
MARCAS_HECHO = (
    "funciona",
    "esta en funcionamiento",
    "se encuentra en funcionamiento",
    "opera",
    "cuenta con",
    "dispone de",
    "se realiza",
    "se realizan",
    "se lleva a cabo",
    "esta vigente",
    "fue inaugurad",
    "inauguro",
    "ya esta",
    "actualmente",
    "todos los",
    "cada ",
)


def _contiene(texto_normalizado: str, agujas) -> bool:
    return any(normalizar_para_cotejo(a) in texto_normalizado for a in agujas)


def menciona_organismo_ajeno(cita: str, subtema: SubTema) -> bool:
    """True si la cita nombra un organismo que no es el municipio."""
    if not subtema.organismos_ajenos:
        return False
    return _contiene(normalizar_para_cotejo(cita), subtema.organismos_ajenos)


def menciona_al_municipio(cita: str) -> bool:
    """True si la cita pone al municipio como sujeto de lo que describe."""
    return _contiene(normalizar_para_cotejo(cita), MARCAS_MUNICIPALES)


def es_anuncio_a_futuro(cita: str) -> bool:
    """True si la cita anuncia algo que todavia no pasa.

    Las marcas de hecho ganan: una cita puede contar el origen de algo que hoy
    funciona sin dejar de ser un hecho.
    """
    normal = normalizar_para_cotejo(cita)
    if _contiene(normal, MARCAS_HECHO):
        return False
    return _contiene(normal, MARCAS_FUTURO)


def clasificar(
    cita: str,
    subtema: SubTema,
    tipo_evidencia: TipoEvidencia,
) -> Estado:
    """Que se puede afirmar con esta cita. Es la unica puerta a CONFIRMADO.

    El orden importa. NO_COMPETE se evalua antes que el tipo de evidencia
    porque es una afirmacion sobre el mundo —lo hace otro organismo— y no sobre
    la calidad de la fuente: vale igual si sale de una ordenanza o de un diario.
    """
    if not cita or len(normalizar_para_cotejo(cita)) < MINIMO_CITA:
        return Estado.SIN_EVIDENCIA

    # 2. La cita habla de un organismo ajeno y no pone al municipio a hacer nada.
    if menciona_organismo_ajeno(cita, subtema) and not menciona_al_municipio(cita):
        return Estado.NO_COMPETE

    # 3. Anuncio a futuro donde se preguntaba por algo en curso.
    if subtema.exige_hecho and es_anuncio_a_futuro(cita):
        return Estado.SIN_EVIDENCIA

    # 1. La prensa nunca confirma politica por si sola.
    if tipo_evidencia is TipoEvidencia.PRENSA:
        return Estado.INDICIO

    return Estado.CONFIRMADO


def conciliar(propuesto: Optional[str], calculado: Estado) -> Estado:
    """Cuando el modelo y el codigo discrepan, gana el mas conservador.

    Misma politica que el motor comercial. El modelo puede sugerir un estado en
    su respuesta; si el codigo llego a uno mas debil, vale el del codigo.
    """
    orden = {
        Estado.SIN_EVIDENCIA: 0,
        Estado.NO_COMPETE: 1,
        Estado.INDICIO: 2,
        Estado.CONFIRMADO: 3,
    }
    try:
        del_modelo = Estado(propuesto) if propuesto else None
    except ValueError:
        del_modelo = None
    if del_modelo is None:
        return calculado
    return min((del_modelo, calculado), key=lambda e: orden[e])


__all__ = [
    "MINIMO_CITA",
    "clasificar",
    "conciliar",
    "es_anuncio_a_futuro",
    "menciona_al_municipio",
    "menciona_organismo_ajeno",
]
