"""
Verificacion de que una cita PRUEBE un proceso manual.

Por que existe: la primera corrida sobre Navarro devolvio 7 oportunidades y solo
1 servia. El modelo estaba tratando "el texto no prueba que sea digital" como si
fuera friccion, y citaba cosas como "debes registrarte en el siguiente link:
Registrarme" — que es exactamente lo contrario de una oportunidad.

Eso es inferir desde la ausencia, que es lo que ADR-0009 prohibe. Y es el mismo
agujero que en Fase 4 dejan las variables si/no: verificar que la cita sea
literal no verifica que la cita pruebe algo.

Entonces se aplica la regla de siempre: **la IA propone, el codigo verifica**.
Una oportunidad solo sobrevive si su cita contiene una accion manual. No alcanza
con que el modelo diga que la hay.

Esto genera falsos negativos —una friccion redactada de forma rara se pierde— y
esta bien. Una lista corta y confiable vale mas que una larga que hay que
auditar: el costo de un prospecto falso es una reunion perdida.
"""

from __future__ import annotations

import re
from typing import Optional

from catalogo import Friccion

# Acciones que PRUEBAN que hoy hay que hacer algo a mano. Son las que convierten
# un texto en evidencia comercial.
_FUERTES = (
    r"dirig[ií]rse",
    r"dirigirse",
    r"acercarse",
    r"acerc[aá]te",
    r"presentarse",
    r"present[aá]ndose",
    r"concurrir",
    r"apersonarse",
    r"retirar(?:se)?\s+(?:el|la|los|las|por)",
    r"orden\s+de\s+llegada",
    r"mesa\s+de\s+entradas",
    r"en\s+forma\s+presencial",
    r"personalmente",
    r"por\s+tel[eé]fono",
    r"comunicarse\s+(?:al|con)",
    r"comunic[aá]te\s+(?:al|con)",
    r"llamar\s+al",
    r"solicitar\s+(?:un\s+)?turno",
    r"pedir\s+(?:un\s+)?turno",
    r"sacar\s+(?:un\s+)?turno",
    r"turnos?\s+telef[oó]nicos?",
    # Un consultorio externo publicado con su telefono ES el mostrador de turnos
    # del hospital: el vecino llama ahi y un administrativo anota a mano. No hay
    # verbo en la cita, pero la friccion esta probada igual.
    r"consultorios?\s+externos?",
    r"turnos?\s+(?:para|de)\s+(?:especialidad|consulta|el\s+hospital)",
    r"admisi[oó]n\s+del\s+(?:centro|hospital)",
    r"debe(?:r[aá]n?)?\s+(?:concurrir|asistir|presentar)",
    r"traer\s+(?:el|la|los|las|dni|documenta)",
    r"con\s+dni",
    r"en\s+ventanilla",
    r"por\s+ventanilla",
    r"imprimir",
    r"formulario\s+en\s+pdf",
)

# Indicios de canal manual sin instruccion explicita: un telefono junto a un
# servicio, una franja horaria de atencion. Sugieren friccion pero no la prueban.
_DEBILES = (
    r"\b(?:0?\d{2,4})[\s\-\.]?\d{3}[\s\-\.]?\d{3,4}\b",   # telefono
    r"\(\d{3,5}\)\s*\d",                                    # (02267) 555222
    r"\bde\s+\d{1,2}(?::\d{2})?\s*(?:a|hasta)\s+\d{1,2}",  # de 8 a 14
    r"\bhorario\s+de\s+atenci[oó]n",
    r"\blunes\s+a\s+viernes\b",
)

# Si la cita muestra que la cosa YA es digital, no es oportunidad por mas que el
# modelo insista. Estas ganan sobre todo lo demas.
_YA_DIGITAL = (
    r"\bregistr[aá](?:rme|te|rse)\b.{0,40}\blink\b",
    r"\bingres[aá]\s+(?:al|a\s+la)\s+(?:sistema|plataforma|portal)",
    r"\bpag[aá]\s+online\b",
    r"\bpago\s+online\b",
    r"\bbot[oó]n\s+de\s+pago\b",
    r"\bturnero\s+online\b",
    r"\bsolicitar\s+(?:el\s+)?turno\s+online\b",
    r"\bcompletar\s+el\s+formulario\s+(?:web|online|en\s+l[ií]nea)",
    r"\bdescargar\s+(?:el\s+)?pliego\b",
    # Si la cita nombra el sistema que UDS vendria a vender, no hay nada que
    # vender. Paso en Pinamar: la cita listaba telefonos y whatsapp de reclamos,
    # pero adentro decia "Sistema Web de Reclamos" — ya lo tienen.
    r"\bsistema\s+web\b",
    r"\bplataforma\s+(?:web|online|digital)\b",
    r"\bautogesti[oó]n\b",
    r"\bventanilla\s+[uú]nica\s+(?:digital|virtual|web)\b",
    r"\bapp\s+(?:municipal|del\s+municipio)\b",
)

_RE_FUERTES = re.compile("|".join(_FUERTES), re.IGNORECASE)
_RE_DEBILES = re.compile("|".join(_DEBILES), re.IGNORECASE)
_RE_YA_DIGITAL = re.compile("|".join(_YA_DIGITAL), re.IGNORECASE)


def friccion_probada(cita: str) -> Optional[Friccion]:
    """Que nivel de friccion prueba esta cita, o None si no prueba ninguna.

    None significa que la cita no sirve como evidencia comercial, sin importar
    lo convincente que suene el razonamiento del modelo.
    """
    if not cita or len(cita.strip()) < 12:
        return None
    if _RE_YA_DIGITAL.search(cita):
        return None  # la cita muestra un canal digital: no es oportunidad
    if _RE_FUERTES.search(cita):
        return Friccion.ALTA
    if _RE_DEBILES.search(cita):
        return Friccion.MEDIA
    return None


def conciliar(propuesta: Friccion, probada: Friccion) -> Friccion:
    """Se queda con la mas conservadora de las dos.

    El modelo puede ver contexto que el regex no (y pedir menos), y el regex
    puede probar lo que el modelo subestimo (pero no se le sube el nivel por
    encima de lo que la cita aguanta).
    """
    orden = {Friccion.BAJA: 0, Friccion.MEDIA: 1, Friccion.ALTA: 2}
    return propuesta if orden[propuesta] < orden[probada] else probada


__all__ = ["friccion_probada", "conciliar"]
