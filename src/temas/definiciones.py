"""
Los temas que se rastrean. Esto es configuracion, no logica.

Agregar un tema es agregar un `Tema` a `TEMAS` y nada mas: el motor, la cosecha,
el prompt y la verificacion son los mismos para todos.

Como se eligen las senales
--------------------------
Una senal es una palabra que hace que valga la pena LEER una pagina, no una
palabra que responda la pregunta. Sirven para dos cosas: elegir que enlaces del
portal cosechar, y priorizar que paginas mandarle al modelo. Que una pagina
diga "ambiente" no confirma nada; solo la hace candidata.

Van sin tildes a proposito: se cotejan contra texto normalizado.
"""

from __future__ import annotations

from typing import Dict, Tuple

from rastreo import SubTema, Tema

# ---------------------------------------------------------------------------
# Ambiental
# ---------------------------------------------------------------------------

PROMOTORES = SubTema(
    id="promotores_ambientales",
    pregunta=(
        "El municipio tiene un programa de promotores ambientales: vecinos o "
        "agentes capacitados que difunden separacion de residuos, cuidado del "
        "arbolado o educacion ambiental en barrios y escuelas?"
    ),
    que_prueba=(
        "La cita tiene que nombrar el programa o a los promotores como algo que "
        "el municipio tiene, capacita o convoca. No alcanza que el municipio "
        "hable de educacion ambiental en general."
    ),
    senales=(
        "promotor ambiental",
        "promotores ambientales",
        "promotoras ambientales",
        "guardia ambiental",
        "educacion ambiental",
        "concientizacion ambiental",
        "brigada ambiental",
        "referente ambiental",
    ),
    queries=(
        '"{municipio}" municipio "promotores ambientales"',
        '"{municipio}" ordenanza "promotor ambiental"',
        '"{municipio}" programa educacion ambiental municipal',
    ),
    # "Se implementara el programa en 2027" no prueba que hoy haya promotores.
    exige_hecho=True,
)

FISCALIZACION_3RA = SubTema(
    id="fiscalizacion_3ra",
    pregunta=(
        "El municipio fiscaliza establecimientos industriales de tercera "
        "categoria (Ley provincial 11.459): inspecciones, habilitaciones, "
        "registro de industrias o convenio de fiscalizacion con la Provincia?"
    ),
    que_prueba=(
        "La cita tiene que mostrar al MUNICIPIO inspeccionando, habilitando o "
        "registrando establecimientos de tercera categoria, o un convenio que le "
        "delegue esa fiscalizacion. Si la cita solo dice que el Certificado de "
        "Aptitud Ambiental lo emite la Provincia, eso NO es fiscalizacion "
        "municipal."
    ),
    senales=(
        "tercera categoria",
        "3ra categoria",
        "11459",
        "11.459",
        "aptitud ambiental",
        "certificado de aptitud",
        "habilitacion industrial",
        "radicacion industrial",
        "nivel de complejidad ambiental",
        "inspeccion industrial",
        "registro de industrias",
    ),
    queries=(
        '"{municipio}" ordenanza "tercera categoria" industria ambiental',
        '"{municipio}" municipio habilitacion industrial "11.459"',
        '"{municipio}" "aptitud ambiental" municipal industria',
    ),
    # "El municipio comenzara a fiscalizar" no prueba que hoy fiscalice.
    exige_hecho=True,
    # Por Ley 11.459 el Certificado de Aptitud Ambiental de las de tercera lo
    # emite OPDS, no el municipio. Sin esta lista, cualquier pagina que explique
    # el tramite provincial se leeria como fiscalizacion municipal.
    organismos_ajenos=(
        "opds",
        "organismo provincial para el desarrollo sostenible",
        "ministerio de ambiente",
        "autoridad del agua",
        "ada",
        "gobierno de la provincia",
        "organismo provincial",
    ),
)

ACCIONES = SubTema(
    id="acciones_ambientales",
    pregunta=(
        "Que acciones ambientales concretas lleva adelante el municipio: "
        "separacion en origen, puntos verdes, compostaje, arbolado urbano, "
        "reciclado, saneamiento de basurales o programas equivalentes?"
    ),
    que_prueba=(
        "La cita tiene que describir una accion que el municipio hace o tiene "
        "andando, no una intencion ni un anuncio a futuro."
    ),
    senales=(
        "separacion en origen",
        "punto verde",
        "puntos verdes",
        "eco punto",
        "ecocanje",
        "compostaje",
        "reciclado",
        "reciclaje",
        "arbolado urbano",
        "plan de arbolado",
        "basural",
        "gestion integral de residuos",
        "girsu",
        "residuos solidos urbanos",
        "planta de reciclado",
        "recuperadores urbanos",
        "huerta agroecologica",
    ),
    queries=(
        '"{municipio}" municipio separacion en origen residuos',
        '"{municipio}" municipio "punto verde" OR compostaje OR reciclado',
        '"{municipio}" municipio plan de arbolado urbano',
    ),
    # Se pregunta por lo que el municipio HACE. Un anuncio de obra futura no
    # cuenta: sin esto, "se construira una planta de reciclado" confirmaba.
    exige_hecho=True,
)

TEMA_AMBIENTAL = Tema(
    id="ambiental",
    nombre="Ambiental",
    descripcion=(
        "Politica ambiental municipal: quien la difunde (promotores), a quien "
        "controla (industrias de tercera categoria) y que hace (acciones)."
    ),
    subtemas=(PROMOTORES, FISCALIZACION_3RA, ACCIONES),
)


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

TEMAS: Dict[str, Tema] = {t.id: t for t in (TEMA_AMBIENTAL,)}


def tema(id_tema: str) -> Tema:
    """Devuelve un tema por id, con un error que dice cuales hay."""
    if id_tema not in TEMAS:
        disponibles = ", ".join(sorted(TEMAS)) or "(ninguno)"
        raise KeyError(f"No existe el tema {id_tema!r}. Disponibles: {disponibles}")
    return TEMAS[id_tema]


def ids_temas() -> Tuple[str, ...]:
    return tuple(sorted(TEMAS))


__all__ = ["TEMAS", "TEMA_AMBIENTAL", "ids_temas", "tema"]
