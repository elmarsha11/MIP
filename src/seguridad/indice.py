"""
Que delitos entran al indice de seguridad, y por que los otros no.

Esta es la decision mas delicada del modulo. El SNIC publica 69 tipos de delito
por partido y NO trae una fila "total": hay que sumar. Sumar los 69 parece lo
neutral y es lo que arruina el numero.

El delito mas frecuente de Chascomus en 2025 es "Tenencia simple atenuada para
uso personal de estupefacientes", con 693 hechos sobre ~2.000 del total. Eso no
mide cuanto delito sufre un vecino: mide **cuanta gente palpa la policia**. Un
partido con despliegue activo en drogas aparece como mas inseguro que uno donde
la policia no sale, que es exactamente al reves.

Por eso el indice se arma con delitos donde hay una VICTIMA que denuncia un
daño, y los demas se informan aparte —no se esconden— porque dicen otra cosa
igual de util: cuanto y como se despliega la fuerza.
"""

from __future__ import annotations

# Delitos con victima: alguien sufrio un daño y lo denuncio. Es lo que la gente
# llama "inseguridad" y lo unico comparable entre partidos.
CONTRA_LAS_PERSONAS = (
    "Homicidios dolosos",
    "Homicidios dolosos en grado de tentativa",
    "Lesiones dolosas",
    "Amenazas",
    "Otros delitos contra las personas",
)

CONTRA_LA_PROPIEDAD = (
    "Robos (excluye los agravados por el resultado de lesiones y/o muertes)",
    "Robos agravados por el resultado de lesiones y/o muertes",
    "Tentativas de robo (excluye las agravadas por el res. de lesiones y/o muerte)",
    "Tentativas de robo agravado por el resultado de lesiones y/o muertes",
    "Hurtos",
    "Tentativas de hurto",
    "Daños (no incluye informáticos)",
    "Otros delitos contra la propiedad",
)

CONTRA_LA_INTEGRIDAD_SEXUAL = (
    "Abusos sexuales con acceso carnal (violaciones)",
    "Abuso sexual agravado",
    "Abuso sexual simple",
    "Tentativa de abuso sexual con acceso carnal",
    "Otros delitos contra la integridad sexual",
)

DELITOS_DEL_INDICE = (
    CONTRA_LAS_PERSONAS + CONTRA_LA_PROPIEDAD + CONTRA_LA_INTEGRIDAD_SEXUAL
)

# Se informan por separado. NO son "menos importantes": miden otra cosa.
#
# Los de estupefacientes y armas son en su enorme mayoria delitos SIN
# denunciante: aparecen porque la policia los detecta. Su tasa es un indicador
# de despliegue policial, que sirve para el eje "como operan" y no para el eje
# "cuanto delito hay".
ACTIVIDAD_POLICIAL = (
    "Tenencia simple atenuada para uso personal de estupefacientes",
    "Tenencia simple de estupefacientes",
    "Tenencia o entrega atenuada de estupefacientes",
    "Comercialización y entrega de estupefacientes",
    "Siembra y producción de estupefacientes",
    "Confabulación de estupefacientes",
    "Otros delitos previstos en la ley 23.737",
    "Portación ilegal de armas de fuego",
    "Tenencia ilegal de armas de fuego",
    "Acopio y fabricación ilegal de armas piezas y municiones",
)

# Fuera de todo indice de seguridad. Un suicidio no es un delito contra un
# tercero y contarlo como "inseguridad" seria un error de categoria, ademas de
# una falta de respeto con el dato. El SNIC lo publica porque su registro pasa
# por la policia, no porque sea delito.
EXCLUIDOS = ("Suicidios (consumados)",)

NIVELES = ("bajo", "medio", "alto")

# Partidos balnearios: en verano reciben mucha mas gente de la que viven.
#
# Por que importa: la tasa del SNIC divide por poblacion RESIDENTE. En un
# balneario los hechos ocurren sobre una poblacion varias veces mayor que el
# denominador, asi que la tasa sale inflada por aritmetica, no por inseguridad.
#
# Medido el 2026-08-12 sobre el ranking 2025: 6 de los 10 primeros son
# balnearios, y 10 de los 29 "alto", siendo apenas 14 de los 86. Sin marcarlos,
# el ranking le dice a un lector que la costa es peligrosa, que es una
# conclusion del denominador.
#
# NO se corrige el numero: corregirlo exigiria poblacion turistica por partido,
# que no tenemos, y estimarla seria inventar (ADR-0009). Se marca y se avisa.
# La lista es geografia verificable, no una estimacion.
POBLACION_ESTACIONAL = frozenset({
    "Villa Gesell",
    "Pinamar",
    "General Alvarado",     # Miramar
    "Monte Hermoso",
    "General Madariaga",    # linda con Pinamar y Villa Gesell
    "General Lavalle",      # linda con la costa de San Clemente
    "Mar Chiquita",         # Santa Clara del Mar
    "Lobería",              # Costa Bonita
    "San Cayetano",
    "Coronel Dorrego",      # Marisol
    "Tres Arroyos",         # Claromeco
    "Coronel Rosales",      # Pehuen Co
    "Patagones",
    "Punta Indio",
})


def clasificar(tasa: float, cortes: tuple) -> str:
    """Nivel de un municipio dada la tasa y los cortes de terciles.

    El nivel es RELATIVO a los 86 del relevamiento, no absoluto: "alto" quiere
    decir "en el tercio superior de los municipios bonaerenses relevados", no
    "peligroso". Presentarlo como absoluto seria afirmar algo que el dato no
    dice.
    """
    bajo, alto = cortes
    if tasa <= bajo:
        return "bajo"
    if tasa >= alto:
        return "alto"
    return "medio"


def cortes_por_terciles(tasas) -> tuple:
    """Los dos cortes que parten la lista en tres grupos parejos."""
    ordenadas = sorted(t for t in tasas if t is not None)
    if len(ordenadas) < 3:
        return (0.0, 0.0)
    n = len(ordenadas)
    return (ordenadas[n // 3], ordenadas[2 * n // 3])


__all__ = [
    "ACTIVIDAD_POLICIAL",
    "CONTRA_LA_INTEGRIDAD_SEXUAL",
    "CONTRA_LA_PROPIEDAD",
    "CONTRA_LAS_PERSONAS",
    "DELITOS_DEL_INDICE",
    "EXCLUIDOS",
    "NIVELES",
    "POBLACION_ESTACIONAL",
    "clasificar",
    "cortes_por_terciles",
]
