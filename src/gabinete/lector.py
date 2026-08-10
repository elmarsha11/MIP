"""
Lectura del gabinete: arma el prompt y verifica lo que vuelve.

Se le da al modelo el texto del boletin y se le pide que devuelva cargo, area,
nombre y la cita literal que lo prueba. El codigo despues comprueba tres cosas,
en este orden:

  1. la cita existe literal en el boletin           (ADR-0014)
  2. el nombre esta adentro de la cita              (handoff §7: verificar el
                                                     valor, no solo la cita)
  3. el nombre no bautiza un edificio               (nombres.py)

El paso 3 es el que no existia en ningun otro modulo de MIP y es el que hace
falta aca: "Centro de Salud Intendente Pedro Carossi" pasa los pasos 1 y 2 sin
problema.

Por que un modelo y no una expresion regular: Chascomus firma "sera refrendado
por el Secretario de Obras (Lucas Funes)", pero Castelli publica 146.000
caracteres sin usar esa formula. Medido el 2026-08-09. El formato varia por
municipio; la pregunta no.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
for _ruta in (_AQUI, _SRC / "extraction"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from modelos import cita_esta_en_fuente  # noqa: E402  (src/extraction/modelos.py)

from autoridades import Autoridad, Cargo, TipoFuente  # noqa: E402
from nombres import nombre_valido_en_cita  # noqa: E402

# Un boletin de Chascomus son 320.000 caracteres. Mandarlos enteros es caro y
# ademas diluye: los nombramientos y las firmas estan en fragmentos cortos y
# reconocibles. Se recorta alrededor de las pistas.
VENTANA = 700
MAX_CHARS_PROMPT = 60_000

# Donde aparecen los cargos en un decreto. No se usan para extraer —eso lo hace
# el modelo— sino para decidir QUE PARTE del boletin vale la pena mandarle.
# NO incluye "refrendado por": esa formula la cubre _RE_FIRMA, que extrae la
# frase sola. Tenerla en las dos listas hacia que el pase de contexto volviera a
# traer todas las firmas ya deduplicadas, fusionadas en un tramo gigante —
# gastando el presupuesto justo en lo que se acababa de deduplicar.
PISTAS = (
    r"secretari[oa]\s+de\s+",
    r"intendente\s+municipal",
    r"design[aá](?:se|ndose|r)?\b",
    r"nombr[aá](?:se|miento)?\b",
    r"asum[eií]",
    r"a\s*cargo\s+de\s+la\s+secretar",
)
_RE_PISTAS = re.compile("|".join(PISTAS), re.IGNORECASE)

# La formula de refrendo, hasta el punto. Un solo decreto puede nombrar a tres
# secretarios de una: "refrendado por el Secretario de Gobierno (X), la
# Secretaria de Seguridad Ciudadana (Y) y la Secretaria de Salud Publica (Z)".
_RE_FIRMA = re.compile(r"refrendad[oa]\s+por\s+[^.]{10,400}", re.IGNORECASE)

ESQUEMA_RESPUESTA = {
    "type": "object",
    "properties": {
        "autoridades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cargo": {"type": "string", "enum": [c.value for c in Cargo]},
                    "area": {
                        "type": "string",
                        "description": (
                            "Area de la secretaria tal como figura en el texto "
                            "('Gobierno', 'Hacienda'). Vacio si es el intendente."
                        ),
                    },
                    "nombre": {
                        "type": "string",
                        "description": "Nombre y apellido completos de la persona.",
                    },
                    "cita_literal": {
                        "type": "string",
                        "description": (
                            "Fragmento copiado EXACTAMENTE del texto donde figura "
                            "esa persona en ese cargo. Tiene que CONTENER el nombre."
                        ),
                    },
                },
                "required": ["cargo", "area", "nombre", "cita_literal"],
            },
        }
    },
    "required": ["autoridades"],
}


def _huella(fragmento: str) -> str:
    """Firma del fragmento para detectar repeticiones.

    Se quedan solo las letras en minuscula: alcanza para ver que dos firmas del
    mismo secretario en dos decretos distintos son el mismo dato, aunque cambien
    los numeros de expediente.
    """
    return re.sub(r"[^a-zñáéíóú ]", "", fragmento.lower())[:180]


def recortar(texto: str, ventana: int = VENTANA, maximo: int = MAX_CHARS_PROMPT) -> str:
    """Los fragmentos del boletin donde puede haber un cargo, sin repetir.

    Dos cosas importan aca, y las dos se aprendieron perdiendo datos:

    1. **Hay que recortar.** Los dos ultimos boletines de Chascomus son 773.000
       caracteres; mandarlos enteros es caro y ademas diluye, porque los cargos
       viven en fragmentos cortos y muy reconocibles.

    2. **Hay que deduplicar.** Un boletin trae ~70 firmas, pero de apenas 5 o 6
       personas: la misma formula se repite en cada decreto. Sin deduplicar, el
       recorte se llenaba de Perez del Cerro repetido y cortaba antes de llegar
       a Moscarella, que aparece dos veces en todo el documento. Se perdian 3 de
       8 secretarias por gastar el presupuesto en repeticiones.

    Los tramos con firma explicita van primero: son la prueba mas dura y la mas
    barata de leer.
    """
    partes, vistas, total = [], set(), 0

    def agregar(fragmento: str) -> None:
        nonlocal total
        h = _huella(fragmento)
        if h in vistas or total + len(fragmento) > maximo:
            return
        vistas.add(h)
        partes.append(fragmento)
        total += len(fragmento)

    # Primero, SOLO la frase de firma, sin el decreto que la rodea. Es donde vive
    # el dato y ocupa ~150 caracteres en vez de 700. Mandar el decreto entero
    # alrededor de cada firma agotaba el presupuesto repitiendo cuerpos de
    # expediente: la Secretaria de Seguridad Ciudadana aparece dos veces en
    # 773.000 caracteres, y las dos quedaban afuera.
    cubierto: List[Tuple[int, int]] = []
    for m in _RE_FIRMA.finditer(texto):
        agregar(m.group(0).strip())
        cubierto.append((m.start(), m.end()))

    def ya_cubierto(a: int, z: int) -> bool:
        """El tramo es, en su mayor parte, firma ya extraida.

        Sin esto el pase de contexto deshacia el trabajo del pase de firmas: la
        pista "Secretario de" tambien esta DENTRO de la formula de refrendo, asi
        que cada firma volvia a entrar con 700 caracteres de decreto alrededor, y
        las repeticiones se fusionaban en un tramo unico que la deduplicacion no
        podia reconocer.
        """
        solapado = sum(max(0, min(z, f) - max(a, i)) for i, f in cubierto)
        return solapado > (z - a) * 0.5

    # Despues, el contexto ancho del resto de las pistas (designaciones,
    # menciones al intendente), que necesitan el entorno para entenderse.
    tramos: List[Tuple[int, int]] = []
    for m in _RE_PISTAS.finditer(texto):
        a, z = max(0, m.start() - ventana // 3), min(len(texto), m.end() + ventana)
        if tramos and a <= tramos[-1][1]:
            tramos[-1] = (tramos[-1][0], max(tramos[-1][1], z))
        else:
            tramos.append((a, z))
    for a, z in tramos:
        if not ya_cubierto(a, z):
            agregar(texto[a:z])

    return "\n[...]\n".join(partes)


def construir_prompt(municipio: str, texto: str) -> str:
    return f"""Sos un analista que lee boletines oficiales municipales.

Del texto de abajo, que es el Boletin Oficial del municipio de {municipio},
extrae QUIEN OCUPA CADA CARGO de la cupula: el intendente y los secretarios.

REGLAS:
1. Cada persona necesita una CITA COPIADA LITERAL del texto, palabra por palabra.
   Se verifica automaticamente contra el original: si no coincide exacto, se
   descarta.
2. La cita tiene que CONTENER el nombre de la persona. Una cita que habla del
   cargo pero no nombra a nadie no sirve.
3. NO incluyas a alguien cuyo nombre solo aparezca bautizando un lugar: "Centro
   de Salud Intendente Pedro Carossi" es un edificio, no el intendente actual.
4. NO incluyas directores, subsecretarios, jefes de departamento ni concejales.
   Solo intendente y secretarios.
5. El area va como figura en el texto: "Gobierno", "Hacienda", "Obras, Servicios
   Publicos y Ambiente". Para el intendente, dejala vacia.
6. Si el texto no nombra a nadie en esos cargos, devolve una lista vacia. Es una
   respuesta correcta: preferimos un vacio honesto a una suposicion.

Un decreto suele decir quien lo refrenda, y eso es la mejor prueba de todas:
"El presente Decreto sera refrendado por el Secretario de Gobierno (Nombre)".

TEXTO DEL BOLETIN OFICIAL DE {municipio.upper()}:

{texto}
"""


def verificar_respuesta(
    respuesta: Optional[dict],
    municipio: str,
    id_municipio: str,
    fuentes: Sequence,
    fecha: str,
    tipo_fuente: TipoFuente = TipoFuente.BOLETIN_OFICIAL,
) -> Tuple[List[Autoridad], int]:
    """Devuelve (autoridades verificadas, cuantas se rechazaron).

    `fuentes` son objetos con .texto y .url: sirve tanto para boletines como para
    paginas de portal, que es la segunda fuente prevista.
    """
    modelo = (respuesta or {}).get("_modelo")
    verificadas: List[Autoridad] = []
    rechazadas = 0
    vistos = set()

    for item in (respuesta or {}).get("autoridades", []) or []:
        try:
            cargo = Cargo(item.get("cargo", ""))
        except ValueError:
            rechazadas += 1
            continue

        nombre = " ".join((item.get("nombre") or "").split())
        cita = " ".join((item.get("cita_literal") or "").split())
        area = " ".join((item.get("area") or "").split()) or None
        if not nombre or not cita:
            rechazadas += 1
            continue

        fuente = next((f for f in fuentes if cita_esta_en_fuente(cita, f.texto)), None)
        if fuente is None:
            rechazadas += 1  # cita inventada o parafraseada
            continue

        # El nombre tiene que estar en la cita Y no puede estar bautizando algo.
        if not nombre_valido_en_cita(nombre, cita):
            rechazadas += 1
            continue

        # Un cargo por municipio: si el modelo repite el area con otra cita, gana
        # la primera. Dos secretarios de Gobierno a la vez es un error de lectura.
        clave = (cargo, (area or "").lower())
        if clave in vistos:
            continue
        vistos.add(clave)

        verificadas.append(
            Autoridad(
                municipio=municipio,
                id_municipio=id_municipio,
                cargo=cargo,
                area=None if cargo is Cargo.INTENDENTE else area,
                nombre=nombre[:120],
                cita=cita[:500],
                url=fuente.url,
                fuente=tipo_fuente,
                fecha=fecha,
                modelo=modelo,
            )
        )

    return verificadas, rechazadas


def leer(
    municipio: str,
    id_municipio: str,
    fuentes: Sequence,
    cliente,
    fecha: str,
    tipo_fuente: TipoFuente = TipoFuente.BOLETIN_OFICIAL,
) -> Tuple[List[Autoridad], int]:
    if not fuentes or cliente is None:
        return [], 0
    texto = recortar("\n".join(f.texto for f in fuentes))
    if not texto.strip():
        return [], 0
    respuesta = cliente.generar_json(construir_prompt(municipio, texto), ESQUEMA_RESPUESTA)
    return verificar_respuesta(
        respuesta, municipio, id_municipio, fuentes, fecha, tipo_fuente
    )


__all__ = ["ESQUEMA_RESPUESTA", "construir_prompt", "leer", "recortar",
           "verificar_respuesta"]
