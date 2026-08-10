"""
Detector de oportunidades: arma el prompt y verifica lo que vuelve.

Misma regla que Fase 4 (ADR-0014): el modelo PROPONE la lectura comercial y el
codigo COMPRUEBA que la cita exista literal en la pagina. Lo que cambia es la
pregunta. Fase 4 pregunta "que dice el portal"; aca se pregunta "que tiene que
hacer hoy un vecino, y podria no hacerlo si el municipio comprara un sistema".

El juicio comercial (que problema es, cuanto duele) no se puede verificar contra
el texto: es interpretacion, y por eso vive en una base aparte y se muestra
siempre junto a su cita. La cita es lo que se verifica; el resto es lectura.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Sequence

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
for _ruta in (_AQUI, _SRC / "extraction"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from modelos import cita_esta_en_fuente, normalizar_para_cotejo  # noqa: E402

from catalogo import CATALOGO, Area, Friccion  # noqa: E402
from comercial import Oportunidad  # noqa: E402
from friccion import conciliar, friccion_probada  # noqa: E402

# Techo por municipio. No es una meta: si hay tres procesos manuales, son tres.
# Existe para que el modelo no rellene con ruido para "completar la lista".
MAX_OPORTUNIDADES = 12

ESQUEMA_RESPUESTA = {
    "type": "object",
    "properties": {
        "oportunidades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "area": {"type": "string", "enum": [a.value for a in Area]},
                    "problema": {
                        "type": "string",
                        "description": (
                            "Que tiene que hacer hoy el vecino o el empleado, en "
                            "una o dos frases, sin jerga tecnica."
                        ),
                    },
                    "friccion": {
                        "type": "string",
                        "enum": [f.value for f in Friccion],
                    },
                    "cita_literal": {
                        "type": "string",
                        "description": (
                            "Fragmento copiado EXACTAMENTE del texto que prueba el "
                            "proceso manual. Palabra por palabra."
                        ),
                    },
                    "pagina": {"type": "integer"},
                },
                "required": ["area", "problema", "friccion", "cita_literal", "pagina"],
            },
        }
    },
    "required": ["oportunidades"],
}


def construir_prompt(municipio: str, paginas: Sequence) -> str:
    bloques = [
        f"--- PAGINA {i} | {p.url}\n{p.texto}" for i, p in enumerate(paginas, start=1)
    ]

    catalogo = "\n".join(
        f"- {p.area.value}: {p.nombre}\n"
        f"    resuelve: {p.resuelve}\n"
        f"    senales: {'; '.join(p.senales)}"
        for p in CATALOGO
    )

    return f"""Sos un consultor de modernizacion municipal. Trabajas para UDS, que
implementa sistemas en municipios de la provincia de Buenos Aires.

Tu trabajo NO es describir que tiene el municipio de {municipio}. Es detectar
QUE PROCESO SIGUE SIENDO MANUAL, porque ahi es donde UDS puede ayudar.

Un proceso manual es cualquier cosa que hoy obliga a una persona a llamar, ir en
persona, esperar, imprimir, o hacer a mano algo que un sistema resolveria.

REGLAS:
1. Cada oportunidad necesita una CITA COPIADA LITERAL del texto de abajo, palabra
   por palabra. Se verifica automaticamente: si no coincide exacto, se descarta.
2. La cita tiene que PROBAR el proceso manual, no solo mencionar el tema. Un
   telefono suelto en un listado de contactos no prueba que haya que llamar para
   sacar turno; "para turnos comunicarse al 4444-5555" si lo prueba.
3. **Que el texto no diga que algo es digital NO es una oportunidad.** La cita
   tiene que mostrar a alguien HACIENDO algo manual: llamar, ir, presentarse,
   esperar, imprimir. Si tu cita no contiene esa accion, no la incluyas. Esto se
   verifica en el codigo y esas propuestas se descartan.
4. No cuentes como oportunidad algo que el texto muestra YA DIGITALIZADO. Si la
   cita dice "registrate en el siguiente link" o "boton de pago", eso es un
   sistema andando, no un problema.
5. Una oportunidad por proceso, no por pagina. Si tres paginas prueban lo mismo,
   es una sola con la mejor cita.
6. **Preferí devolver 2 oportunidades solidas antes que 8 flojas.** No hay que
   llenar la lista: un municipio con un solo proceso manual probado tiene una
   sola oportunidad, y eso es una respuesta correcta y util.

COMO GRADUAR LA FRICCION:
- alta  : el texto prueba que hay que ir, llamar o esperar SI O SI. Ej: "dirigirse
          a mesa de entradas", "por orden de llegada", "para turnos llamar al...".
- media : hay un canal manual publicado y ningun canal digital a la vista, pero
          el texto no prueba que sea el unico camino.
- baja  : indicio suelto. Un telefono o un horario, sin proceso descrito.
          Ante la duda entre media y baja, elegi baja.

AREAS Y QUE VENDE UDS EN CADA UNA:
{catalogo}

Devolve como maximo {MAX_OPORTUNIDADES} oportunidades, las mas fuertes primero.

TEXTO DE LAS PAGINAS OFICIALES DE {municipio.upper()}:

{chr(10).join(bloques)}
"""


def _pagina_de_la_cita(cita: str, paginas: Sequence, indice: Optional[int]):
    """Igual que Fase 4: se confia en el numero de pagina, pero se verifica.

    Equivocarse de numero es un desliz; inventar la cita no lo es.
    """
    if isinstance(indice, int) and 1 <= indice <= len(paginas):
        candidata = paginas[indice - 1]
        if cita_esta_en_fuente(cita, candidata.texto):
            return candidata
    for p in paginas:
        if cita_esta_en_fuente(cita, p.texto):
            return p
    return None


def verificar_respuesta(
    respuesta: Optional[dict],
    municipio: str,
    id_municipio: str,
    paginas: Sequence,
    fecha: str,
) -> tuple:
    """Devuelve (oportunidades verificadas, cuantas citas se rechazaron)."""
    from catalogo import POR_AREA

    modelo = (respuesta or {}).get("_modelo")
    verificadas: List[Oportunidad] = []
    rechazadas = 0
    vistas = set()
    citas_vistas = set()

    for item in (respuesta or {}).get("oportunidades", []) or []:
        try:
            area = Area(item.get("area", ""))
            friccion = Friccion(item.get("friccion", ""))
        except ValueError:
            rechazadas += 1  # area o friccion fuera del contrato
            continue

        cita = (item.get("cita_literal") or "").strip()
        problema = (item.get("problema") or "").strip()
        if not cita or not problema:
            rechazadas += 1
            continue

        pagina = _pagina_de_la_cita(cita, paginas, item.get("pagina"))
        if pagina is None:
            rechazadas += 1  # el modelo la invento o la parafraseo
            continue

        # Que la cita sea literal no prueba que haya friccion. El modelo tiende a
        # leer "el texto no dice que sea digital" como oportunidad, y eso es
        # inferir desde la ausencia (ADR-0009). Acá el codigo exige que la cita
        # contenga una accion manual, y si no la tiene la oportunidad se cae.
        probada = friccion_probada(cita)
        if probada is None:
            rechazadas += 1
            continue
        friccion = conciliar(friccion, probada)

        # Una sola oportunidad por area: si el modelo repite el mismo proceso
        # con distinta cita, gana la primera (vienen ordenadas por fuerza).
        if area in vistas:
            continue

        # Y una sola por CITA. Sin esto, una misma frase se recicla para varias
        # areas y el puntaje se infla: Carmen de Areco quedaba primero en el
        # ranking con 4 oportunidades que eran 2 evidencias contadas dos veces
        # ("Mesa de entradas Moreno 541" servia de prueba para tramites y para
        # expedientes). Un ranking inflado manda al equipo comercial al
        # municipio equivocado, que es exactamente lo que hay que evitar.
        huella = normalizar_para_cotejo(cita)[:160]
        if huella in citas_vistas:
            continue

        vistas.add(area)
        citas_vistas.add(huella)

        verificadas.append(
            Oportunidad(
                municipio=municipio,
                id_municipio=id_municipio,
                area=area,
                problema=problema[:400],
                friccion=friccion,
                cita=cita[:500],
                url=pagina.url,
                producto=POR_AREA[area].nombre,
                fecha=fecha,
                modelo=modelo,
            )
        )

    return verificadas, rechazadas


def detectar(
    municipio: str,
    id_municipio: str,
    paginas: Sequence,
    cliente,
    fecha: str,
) -> tuple:
    if not paginas or cliente is None:
        return [], 0
    respuesta = cliente.generar_json(construir_prompt(municipio, paginas), ESQUEMA_RESPUESTA)
    return verificar_respuesta(respuesta, municipio, id_municipio, paginas, fecha)


__all__ = ["ESQUEMA_RESPUESTA", "construir_prompt", "detectar", "verificar_respuesta"]
