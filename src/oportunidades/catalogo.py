"""
Catalogo de areas donde UDS vende, y las senales que delatan una oportunidad.

Esto NO es un esquema de datos como el de Fase 4. Fase 4 pregunta "que dice el
portal". Aca la pregunta es otra: **que proceso manual revela el portal que UDS
pueda digitalizar**.

La diferencia importa. Fase 4 registra bien lo que HAY y casi nada de lo que
FALTA: al 2026-08-09, boletin_oficial da 86/86 "si" y pago_online_tasas da 39
"si" contra CERO "no". Para vender, el prospecto es justamente la ausencia. Por
eso este modulo no lee variables: lee el texto de las paginas buscando la
friccion.

Una friccion es una frase que prueba que hoy alguien tiene que llamar, ir,
esperar o hacer a mano algo que un sistema podria resolver.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple, Tuple


class Area(str, Enum):
    """Areas de intervencion de UDS."""

    SALUD = "salud"
    TRIBUTARIA = "tributaria"
    TRAMITES = "tramites"
    EXPEDIENTES = "expedientes"
    RECLAMOS = "reclamos"
    MEDIO_AMBIENTE = "medio_ambiente"
    TURISMO = "turismo"
    EDUCACION = "educacion"
    INTERNA = "interna"
    TRANSPARENCIA = "transparencia"


class Friccion(str, Enum):
    """Cuanto duele el proceso actual. Ordena el trabajo comercial.

    No es lo mismo una prueba de que hay que ir en persona que un telefono
    suelto en un directorio de contactos. Igualar los dos convierte la lista de
    prospectos en ruido, que es exactamente lo que hay que evitar.
    """

    ALTA = "alta"      # el texto prueba que hay que ir, llamar o esperar si o si
    MEDIA = "media"    # hay canal manual pero podria haber otro no publicado
    BAJA = "baja"      # indicio suelto: un telefono, un horario, sin proceso claro


class ProductoUDS(NamedTuple):
    area: Area
    nombre: str
    # Que problema resuelve, en la lengua del intendente y no en la del sistema.
    resuelve: str
    # Que buscar en el texto. Son PISTAS para el modelo, no reglas de matcheo:
    # el modelo tiene que entender la situacion, no encontrar la palabra.
    senales: Tuple[str, ...]


# El catalogo sale de lo que UDS efectivamente implementa. Si UDS no lo vende,
# no va aca: una oportunidad que nadie puede atender no es una oportunidad.
CATALOGO: Tuple[ProductoUDS, ...] = (
    ProductoUDS(
        area=Area.SALUD,
        nombre="Turnero de salud online",
        resuelve=(
            "El vecino saca turno eligiendo medico, dia y hora, sin llamar ni ir. "
            "El administrativo deja de atender el telefono y anotar a mano: entra "
            "al sistema, ve los turnos del medico y los imprime. Si el vecino "
            "prefiere ir presencial, el administrativo carga el turno en la misma "
            "plataforma, asi no quedan dos agendas."
        ),
        senales=(
            "turnos por telefono o WhatsApp",
            "hay que acercarse a mesa de entradas o admision para sacar turno",
            "atencion por orden de llegada",
            "franja horaria acotada para pedir turnos (ej: de 8 a 14)",
            "un numero de consultorios externos publicado",
        ),
    ),
    ProductoUDS(
        area=Area.TRIBUTARIA,
        nombre="Pago de tasas online",
        resuelve=(
            "El vecino consulta deuda y paga desde el celular. El municipio deja "
            "de depender de la ventanilla y de la cola de fin de mes."
        ),
        senales=(
            "hay que ir a la oficina de rentas o tesoreria a pagar",
            "la boleta se retira en el municipio",
            "solo se informa un horario de caja",
            "se paga en un banco o entidad presencial",
        ),
    ),
    ProductoUDS(
        area=Area.TRAMITES,
        nombre="Ventanilla unica de tramites",
        resuelve=(
            "Un solo lugar para iniciar y seguir cualquier tramite, con estado "
            "visible. Hoy el vecino no sabe donde esta su tramite y vuelve a "
            "preguntar en persona."
        ),
        senales=(
            "hay que presentarse con DNI o documentacion en papel",
            "el tramite se inicia en una oficina especifica",
            "se pide enviar un mail y esperar respuesta",
            "requisitos publicados pero sin forma de iniciar en linea",
        ),
    ),
    ProductoUDS(
        area=Area.EXPEDIENTES,
        nombre="Expediente digital",
        resuelve=(
            "El expediente deja de moverse en papel entre oficinas. Se sabe donde "
            "esta y quien lo tiene."
        ),
        senales=(
            "mesa de entradas presencial",
            "presentacion de notas o expedientes en papel",
            "se menciona circuito entre secretarias sin sistema",
        ),
    ),
    ProductoUDS(
        area=Area.RECLAMOS,
        nombre="Gestion de reclamos con seguimiento",
        resuelve=(
            "El reclamo entra por un canal, tiene numero y el vecino ve en que "
            "estado esta. Hoy se pierde entre telefono, Facebook y WhatsApp."
        ),
        senales=(
            "reclamos por telefono, WhatsApp o redes sociales",
            "no hay numero de seguimiento",
            "se pide concurrir a la oficina a reclamar",
        ),
    ),
    ProductoUDS(
        area=Area.MEDIO_AMBIENTE,
        nombre="Gestion ambiental digital",
        resuelve=(
            "Turnos de recoleccion, denuncias ambientales y trazabilidad de "
            "residuos en un sistema, no en un telefono."
        ),
        senales=(
            "retiro de residuos voluminosos coordinado por telefono",
            "denuncias ambientales presenciales",
            "cronogramas de recoleccion publicados solo como imagen o PDF",
        ),
    ),
    ProductoUDS(
        area=Area.TURISMO,
        nombre="Portal turistico y reservas",
        resuelve=(
            "El municipio publica su oferta y toma reservas. Sin sitio propio, el "
            "turista no encuentra nada oficial."
        ),
        senales=(
            "no hay sitio de turismo propio",
            "la informacion turistica esta solo en redes sociales",
            "reservas de campings o alojamiento municipal por telefono",
        ),
    ),
    ProductoUDS(
        area=Area.EDUCACION,
        nombre="Gestion educativa municipal",
        resuelve=(
            "Inscripciones y becas en linea, sin fila ni formulario en papel."
        ),
        senales=(
            "inscripciones presenciales a cursos, talleres o becas",
            "formularios en PDF para imprimir",
            "cupos por orden de llegada",
        ),
    ),
    ProductoUDS(
        area=Area.INTERNA,
        nombre="Integracion entre areas del municipio",
        resuelve=(
            "Las secretarias comparten datos en vez de pedirselos por nota. Es lo "
            "que evita que el vecino tenga que llevar el mismo papel a tres "
            "oficinas."
        ),
        senales=(
            "el vecino tiene que ir a mas de un area por el mismo tramite",
            "se pide presentar constancia emitida por otra oficina del municipio",
            "cada secretaria publica su propio telefono y horario sin canal comun",
        ),
    ),
    ProductoUDS(
        area=Area.TRANSPARENCIA,
        nombre="Portal de transparencia",
        resuelve=(
            "Presupuesto, licitaciones y normativa publicados y buscables. Baja "
            "los pedidos de informacion y las notas de prensa negativas."
        ),
        senales=(
            "informacion presupuestaria solo en PDF sueltos",
            "licitaciones publicadas sin pliego descargable",
            "no hay seccion de transparencia",
        ),
    ),
)

POR_AREA = {p.area: p for p in CATALOGO}

__all__ = ["Area", "Friccion", "ProductoUDS", "CATALOGO", "POR_AREA"]
