"""
Fase 4 - Extraccion verificada.

Aca vive la regla de ADR-0014: la IA propone, el codigo verifica.

Gemini recibe unicamente el texto de las paginas que Fase 3 valido, y para cada
variable devuelve un valor mas una **cita textual**. Despues, `_verificar()`
comprueba que esa cita exista literalmente en el texto que se le dio. Si no
existe, el hallazgo se descarta y la variable queda no_verificable.

Una alucinacion no puede sobrevivir a eso: para pasar tendria que inventar una
cita que ademas este textualmente en la pagina, y eso ya no es alucinar.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

try:
    from .fetcher import Pagina
    from .modelos import (
        DOMINIO_VALORES,
        CanalTurnos,
        Confianza,
        EstadoHallazgo,
        Hallazgo,
        TipoFuente,
        Valor,
        Variable,
        cita_esta_en_fuente,
        es_texto_libre,
        valor_respaldado_por_la_cita,
    )
except ImportError:  # ejecutado como script
    from fetcher import Pagina  # type: ignore[no-redef]
    from modelos import (  # type: ignore[no-redef]
        DOMINIO_VALORES,
        CanalTurnos,
        Confianza,
        EstadoHallazgo,
        Hallazgo,
        TipoFuente,
        Valor,
        Variable,
        cita_esta_en_fuente,
        es_texto_libre,
        valor_respaldado_por_la_cita,
    )

# ---------------------------------------------------------------------------
# Que se le pregunta al modelo
# ---------------------------------------------------------------------------

# Las definiciones salen de schemas/diccionario_datos_oficial_v1.md. Son
# deliberadamente exigentes: "tiene una pagina de salud" no es "tiene turnos
# online". El diccionario pide URL de turnero funcional.
PREGUNTAS: Dict[Variable, str] = {
    Variable.TRAMITES_ONLINE: (
        "El portal permite iniciar o completar tramites por internet (no solo "
        "informar horarios o requisitos). En 'detalle', listá los tramites nombrados."
    ),
    Variable.TURNOS_SALUD_ONLINE: (
        "Se puede pedir un turno medico (hospital, CAPS, especialidad) SIN ir "
        "personalmente ni llamar por telefono: formulario web, turnero online, "
        "app municipal, WhatsApp, Telegram o mail. Un numero de WhatsApp para "
        "sacar turnos CUENTA como si. Los turnos de licencia de conducir NO "
        "cuentan, son de transito. 'Acercate al CAPS' o solo un telefono fijo es 'no'."
    ),
    Variable.CANAL_TURNOS_SALUD: (
        "Por que canal se pide el turno medico. Valores: web (formulario o "
        "turnero propio), whatsapp, telegram, app, email, telefono (hay que "
        "llamar), presencial (hay que ir). Si no se puede determinar, "
        "no_verificable. En 'detalle', el numero o link si figura."
    ),
    Variable.PAGO_ONLINE_TASAS: (
        "Se pueden pagar tasas municipales por internet: boton de pago, homebanking, "
        "Mercado Pago, Red Link, Pago Facil online, cuenta corriente tributaria."
    ),
    Variable.SISTEMA_RAFAM: "Se menciona el sistema RAFAM de administracion financiera municipal.",
    Variable.EXPEDIENTE_DIGITAL_GDE: (
        "Hay expediente digital, GDE, mesa de entradas digital o tramites a distancia."
    ),
    Variable.RECLAMOS_147: (
        "Hay un canal de reclamos urbanos: linea 147, formulario de reclamos, "
        "app de reclamos o atencion ciudadana online."
    ),
    Variable.TRANSPARENCIA_PRESUPUESTO: (
        "Se publica el presupuesto municipal o la rendicion de cuentas."
    ),
    Variable.BOLETIN_OFICIAL: "Se publica el boletin oficial municipal o se enlaza al SIBOM.",
    Variable.LICITACIONES: "Se publican licitaciones, compras o contrataciones.",
    Variable.APP_MUNICIPAL: (
        "El municipio tiene una app movil propia. En 'detalle', el nombre exacto de la app."
    ),
    Variable.INTENDENTE: "Nombre completo del Intendente actual del municipio.",
    Variable.SECRETARIAS: "Nombres de los secretarios y las secretarías a su cargo.",
    Variable.CONCEJALES: "Información sobre los concejales o el Honorable Concejo Deliberante.",
    Variable.POBLACION: "Datos demográficos, cantidad de habitantes, viviendas, etc.",
    Variable.HOSPITALES_CAPS: "Nombres de hospitales, CAPS (Centros de Atención Primaria) o centros de salud.",
    Variable.INSTITUCIONES_EDUCATIVAS: "Escuelas, jardines, polos educativos, o instituciones educativas mencionadas.",
    Variable.MEDIO_AMBIENTE: "Planes ambientales, centros de reciclaje, o información sobre medio ambiente.",
    Variable.SEGURIDAD_VIGILANCIA: "Cámaras de seguridad, centro de monitoreo, o aplicaciones de seguridad locales.",
    Variable.TRANSPORTE_PUBLICO: "Líneas de colectivos locales, trenes o transporte público mencionado.",
}

ESQUEMA_RESPUESTA = {
    "type": "object",
    "properties": {
        "hallazgos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "variable": {"type": "string", "enum": [v.value for v in Variable]},
                    # Sin enum fijo: cada variable tiene su propio dominio
                    # (canal_turnos_salud admite whatsapp, telegram, web...).
                    # El valor se valida contra DOMINIO_VALORES en el codigo.
                    "valor": {"type": "string"},
                    "cita_literal": {
                        "type": "string",
                        "description": (
                            "Fragmento copiado EXACTAMENTE del texto, palabra por "
                            "palabra. Vacio si el valor es no_verificable."
                        ),
                    },
                    "pagina": {
                        "type": "integer",
                        "description": "Numero de PAGINA de donde se copio la cita",
                    },
                    "detalle": {
                        "type": "string",
                        "description": "Lista de tramites o nombre de la app. Vacio si no aplica.",
                    },
                },
                "required": ["variable", "valor", "cita_literal", "pagina", "detalle"],
            },
        }
    },
    "required": ["hallazgos"],
}


def construir_prompt(
    municipio: str, paginas: Sequence[Pagina], variables: Optional[Sequence[Variable]] = None
) -> str:
    variables = list(variables) if variables is not None else list(Variable)
    bloques = []
    for i, p in enumerate(paginas, start=1):
        bloques.append(f"--- PAGINA {i} | tipo: {p.tipo} | {p.url}\n{p.texto}")
    texto_paginas = "\n\n".join(bloques)

    # El esquema de respuesta no fija un enum (cada variable tiene su dominio),
    # asi que los valores admitidos se declaran aca. Sin esto el modelo inventa
    # etiquetas y el codigo se las rechaza despues, gastando una llamada al pedo.
    def _linea(v: Variable) -> str:
        admitidos = DOMINIO_VALORES[v]
        dominio = "texto libre, copiado del texto" if admitidos is None else "/".join(admitidos)
        return f"- {v.value} (valores: {dominio}): {PREGUNTAS[v]}"

    preguntas = "\n".join(_linea(v) for v in variables)

    return f"""Sos un auditor de transformacion digital municipal. Tu unico trabajo es
leer el texto que sigue y reportar QUE DICE, sin agregar nada de tu conocimiento
previo sobre el municipio de {municipio}.

REGLAS ESTRICTAS:
1. Solo podes afirmar algo que este ESCRITO en el texto de abajo.
2. Toda respuesta "si" o "no" necesita una CITA COPIADA LITERAL del texto,
   palabra por palabra, sin reescribir ni resumir. Se verifica automaticamente
   contra el original: si la cita no coincide exactamente, se descarta el dato.
3. Si el texto no alcanza para decidir, respondé "no_verificable" con cita vacia.
   Es una respuesta CORRECTA y esperada, no un fracaso. Preferimos un vacio
   honesto a una suposicion.
4. No infieras. Que un municipio tenga portal no significa que tenga turnos online.
5. "no" solo si el texto evidencia la ausencia (ej: "los turnos se retiran
   personalmente"). Si simplemente no se menciona, es "no_verificable".

VARIABLES A REPORTAR (una entrada por cada una, las {len(variables)}):
{preguntas}

TEXTO DE LAS PAGINAS OFICIALES DE {municipio.upper()}:

{texto_paginas}
"""


# ---------------------------------------------------------------------------
# Verificacion
# ---------------------------------------------------------------------------


def _confianza(pagina: Pagina) -> Confianza:
    """Alta solo si la evidencia salio del portal oficial acreditado por Fase 3."""
    if pagina.tipo_fuente is TipoFuente.PORTAL_OFICIAL and pagina.confianza_url == "Alta":
        return Confianza.ALTA
    return Confianza.MEDIA


def _hallazgo_vacio(
    municipio: str, id_municipio: str, variable: Variable, fecha: str,
    modelo: Optional[str], estado: EstadoHallazgo,
) -> Hallazgo:
    return Hallazgo(
        municipio=municipio,
        id_municipio=id_municipio,
        variable=variable,
        valor=Valor.NO_VERIFICABLE.value,
        fecha=fecha,
        confianza=Confianza.CERO,
        estado=estado,
        modelo=modelo,
    )


def verificar_respuesta(
    respuesta: Optional[dict],
    municipio: str,
    id_municipio: str,
    paginas: Sequence[Pagina],
    fecha: str,
) -> List[Hallazgo]:
    """Convierte la respuesta del modelo en hallazgos, verificando cada cita.

    Toda variable aparece en la salida, tenga dato o no: ADR-0009 exige que el
    vacio se vea, no que desaparezca.
    """
    modelo = (respuesta or {}).get("_modelo")
    propuestos = {}
    for item in (respuesta or {}).get("hallazgos", []) or []:
        try:
            propuestos[Variable(item.get("variable", ""))] = item
        except ValueError:
            continue  # variable fuera del enum: se ignora

    hallazgos: List[Hallazgo] = []
    for variable in Variable:
        item = propuestos.get(variable)

        if item is None:
            hallazgos.append(
                _hallazgo_vacio(
                    municipio, id_municipio, variable, fecha, modelo,
                    EstadoHallazgo.NO_VERIFICABLE,
                )
            )
            continue

        valor = (item.get("valor") or "").strip()
        cita = (item.get("cita_literal") or "").strip()

        admitidos = DOMINIO_VALORES[variable]
        if admitidos is not None and valor not in admitidos:
            # El modelo invento un valor que no esta en el contrato ("parcial",
            # "quizas"). No se traduce ni se interpreta: queda sin dato.
            hallazgos.append(
                _hallazgo_vacio(
                    municipio, id_municipio, variable, fecha, modelo,
                    EstadoHallazgo.NO_VERIFICABLE,
                )
            )
            continue

        if valor == Valor.NO_VERIFICABLE.value or not cita:
            hallazgos.append(
                _hallazgo_vacio(
                    municipio, id_municipio, variable, fecha, modelo,
                    EstadoHallazgo.NO_VERIFICABLE,
                )
            )
            continue

        # --- el corazon de ADR-0014 ---------------------------------------
        # Se busca la cita en la pagina que el modelo indico y, si no esta, en
        # todas. Confundirse de numero de pagina es un desliz; inventar la cita no.
        # En las variables de texto libre el valor es el dato, no una etiqueta
        # de un dominio cerrado. Tiene que estar en la cita o no vale.
        if es_texto_libre(variable) and not valor_respaldado_por_la_cita(valor, cita):
            hallazgos.append(
                _hallazgo_vacio(
                    municipio, id_municipio, variable, fecha, modelo,
                    EstadoHallazgo.CITA_RECHAZADA,
                )
            )
            continue

        pagina = _buscar_pagina_con_la_cita(cita, paginas, item.get("pagina"))
        if pagina is None:
            hallazgos.append(
                _hallazgo_vacio(
                    municipio, id_municipio, variable, fecha, modelo,
                    EstadoHallazgo.CITA_RECHAZADA,
                )
            )
            continue

        detalle = (item.get("detalle") or "").strip() or None
        hallazgos.append(
            Hallazgo(
                municipio=municipio,
                id_municipio=id_municipio,
                variable=variable,
                valor=valor,
                detalle=detalle,
                url=pagina.url,
                fecha=fecha,
                fragmento=cita[:500],
                tipo_fuente=pagina.tipo_fuente,
                confianza=_confianza(pagina),
                estado=EstadoHallazgo.VERIFICADO,
                modelo=modelo,
            )
        )
    return hallazgos


def _buscar_pagina_con_la_cita(
    cita: str, paginas: Sequence[Pagina], indice: Optional[int]
) -> Optional[Pagina]:
    if isinstance(indice, int) and 1 <= indice <= len(paginas):
        candidata = paginas[indice - 1]
        if cita_esta_en_fuente(cita, candidata.texto):
            return candidata
    for pagina in paginas:
        if cita_esta_en_fuente(cita, pagina.texto):
            return pagina
    return None


# ---------------------------------------------------------------------------
# Lo que se responde sin IA
# ---------------------------------------------------------------------------

# Tipo de URL que, por si solo, prueba la variable. Si Fase 3 valido una URL de
# tipo licitaciones con su fragmento, el municipio publica licitaciones: no hace
# falta preguntarle a un modelo algo que ya esta probado con evidencia mas dura.
#
# Los tipos que NO alcanzan quedan afuera a proposito. El caso testigo es
# salud_turnos: tener una pagina de salud no es tener turnos online, y el
# diccionario es explicito al respecto. Esa distincion la tiene que hacer la IA
# leyendo el texto.
TIPO_PRUEBA_VARIABLE = {
    "boletin_sibom": Variable.BOLETIN_OFICIAL,
    "licitaciones": Variable.LICITACIONES,
    "reclamos_147": Variable.RECLAMOS_147,
    "gde_expediente": Variable.EXPEDIENTE_DIGITAL_GDE,
    "play_store": Variable.APP_MUNICIPAL,
    "app_store": Variable.APP_MUNICIPAL,
}

TIPO_A_FUENTE_HALLAZGO = {
    "boletin_sibom": TipoFuente.REGISTRO_PROVINCIAL,
    "play_store": TipoFuente.STORE_APP,
    "app_store": TipoFuente.STORE_APP,
}


def hallazgos_deterministicos(
    urls_tipificadas, municipio: str, id_municipio: str, fecha: str
) -> Dict[Variable, Hallazgo]:
    """Variables que se responden con lo que Fase 3 ya probo, sin IA."""
    encontrados: Dict[Variable, Hallazgo] = {}
    for u in urls_tipificadas:
        variable = TIPO_PRUEBA_VARIABLE.get(u.tipo)
        if variable is None or variable in encontrados:
            continue
        if not u.fragmento or u.confianza not in ("Alta", "Media"):
            continue  # ADR-0009: sin evidencia no hay dato
        encontrados[variable] = Hallazgo(
            municipio=municipio,
            id_municipio=id_municipio,
            variable=variable,
            valor=Valor.SI.value,
            url=u.url,
            fecha=fecha,
            fragmento=u.fragmento[:500],
            tipo_fuente=TIPO_A_FUENTE_HALLAZGO.get(u.tipo, TipoFuente.PORTAL_OFICIAL),
            confianza=Confianza.ALTA if u.confianza == "Alta" else Confianza.MEDIA,
            estado=EstadoHallazgo.VERIFICADO,
            modelo=None,  # sin IA: lo probo Fase 3
        )
    return encontrados


def extraer(
    municipio: str,
    id_municipio: str,
    paginas: Sequence[Pagina],
    cliente,
    fecha: str,
    urls_tipificadas: Sequence = (),
) -> List[Hallazgo]:
    """Primero lo que se prueba solo, despues una unica llamada de IA por el resto."""
    ya_probadas = hallazgos_deterministicos(urls_tipificadas, municipio, id_municipio, fecha)

    if not paginas or cliente is None:
        de_ia = [
            _hallazgo_vacio(
                municipio, id_municipio, v, fecha, None, EstadoHallazgo.NO_VERIFICABLE
            )
            for v in Variable
            if v not in ya_probadas
        ]
    else:
        pendientes = [v for v in Variable if v not in ya_probadas]
        respuesta = cliente.generar_json(
            construir_prompt(municipio, paginas, pendientes), ESQUEMA_RESPUESTA
        )
        de_ia = [
            h
            for h in verificar_respuesta(
                respuesta, municipio, id_municipio, paginas, fecha
            )
            if h.variable not in ya_probadas
        ]

    # Orden estable: el del enum, para que la salida sea comparable entre corridas.
    por_variable = {h.variable: h for h in de_ia}
    por_variable.update(ya_probadas)
    return [por_variable[v] for v in Variable if v in por_variable]


__all__ = [
    "ESQUEMA_RESPUESTA",
    "PREGUNTAS",
    "construir_prompt",
    "extraer",
    "verificar_respuesta",
]
