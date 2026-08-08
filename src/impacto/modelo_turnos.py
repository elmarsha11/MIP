"""
Fase 5 - Costo de no tener turnos de salud online.

Reemplaza a la constante de $31.001 por habitante. La diferencia no es la
formula: es que cada insumo trae su fuente y el resultado sale como rango.

Dos numeros distintos, y no se mezclan:

  COSTO SOCIAL   horas que pierden los vecinos x valor de esa hora.
                 NO es plata del presupuesto municipal. Un intendente no la
                 paga ni la ahorra: se la devuelve a sus vecinos. Es el
                 argumento politico y el que le interesa a CAF o al FRICDe.

  COSTO FISCAL   minutos de empleado municipal atendiendo la ventanilla x su
                 costo laboral. ESO si es presupuesto. Todavia no se calcula:
                 hace falta la escala salarial municipal publicada, que no
                 tenemos. Se declara pendiente en vez de estimarse.

Confundir los dos es el error que un contador detecta en cinco minutos, y ahi
se cae la credibilidad de todo lo demas.

Solo se calcula sobre municipios donde MIP PROBO la ausencia con cita textual
(canal telefono o presencial). Nunca sobre un no_verificable: no saber si un
municipio tiene turnero no es lo mismo que saber que no lo tiene.
"""

from __future__ import annotations

from typing import List, NamedTuple, Optional

try:
    from .parametros import (
        CONSULTAS_MEDICAS_POR_HABITANTE,
        HORAS_POR_TURNO_PRESENCIAL,
        PROPORCION_TURNOS_GESTIONADOS,
        VALOR_HORA_VECINO,
        Parametro,
        TipoParametro,
    )
except ImportError:  # ejecutado como script
    from parametros import (  # type: ignore[no-redef]
        CONSULTAS_MEDICAS_POR_HABITANTE,
        HORAS_POR_TURNO_PRESENCIAL,
        PROPORCION_TURNOS_GESTIONADOS,
        VALOR_HORA_VECINO,
        Parametro,
        TipoParametro,
    )


class CostoSocial(NamedTuple):
    """Costo anual, expresado como rango porque hay supuestos en el medio."""

    municipio: str
    id_municipio: str
    poblacion: int
    canal_actual: str
    evidencia: str
    url: Optional[str]

    turnos_anuales_min: float
    turnos_anuales_max: float
    horas_perdidas_min: float
    horas_perdidas_max: float
    costo_min: float
    costo_central: float
    costo_max: float

    @property
    def es_estimacion(self) -> bool:
        """Siempre True mientras haya supuestos sin fuente. No se puede afirmar."""
        return True

    def por_habitante(self) -> float:
        return self.costo_central / self.poblacion if self.poblacion else 0.0


def _rango(p: Parametro) -> tuple:
    return p.rango()


def calcular(
    municipio: str,
    id_municipio: str,
    poblacion: int,
    canal_actual: str,
    evidencia: str,
    url: Optional[str] = None,
) -> CostoSocial:
    """Costo social anual de gestionar turnos sin canal digital.

    Cadena de calculo, de abajo hacia arriba:

        consultas anuales   = poblacion x consultas por habitante
        turnos a gestionar  = consultas x proporcion que requiere turno
        horas perdidas      = turnos x horas por turno presencial
        costo social        = horas x valor hora (SMVM)

    Todos los pasos menos el ultimo descansan en supuestos declarados, asi que
    la salida es un rango. El unico parametro con fuente oficial es el valor
    hora, y es a proposito el mas bajo defendible.
    """
    c_min, c_cen, c_max = _rango(CONSULTAS_MEDICAS_POR_HABITANTE)
    p_min, p_cen, p_max = _rango(PROPORCION_TURNOS_GESTIONADOS)
    h_min, h_cen, h_max = _rango(HORAS_POR_TURNO_PRESENCIAL)
    valor_hora = VALOR_HORA_VECINO.valor or 0.0

    turnos_min = poblacion * c_min * p_min
    turnos_cen = poblacion * c_cen * p_cen
    turnos_max = poblacion * c_max * p_max

    return CostoSocial(
        municipio=municipio,
        id_municipio=id_municipio,
        poblacion=poblacion,
        canal_actual=canal_actual,
        evidencia=evidencia,
        url=url,
        turnos_anuales_min=turnos_min,
        turnos_anuales_max=turnos_max,
        horas_perdidas_min=turnos_min * h_min,
        horas_perdidas_max=turnos_max * h_max,
        costo_min=turnos_min * h_min * valor_hora,
        costo_central=turnos_cen * h_cen * valor_hora,
        costo_max=turnos_max * h_max * valor_hora,
    )


def techo_de_precio_anual(costo: CostoSocial, fraccion_del_valor: float = 0.10) -> tuple:
    """Cuanto puede justificar pagar este municipio, como rango.

    UDS todavia no tiene precio definido, asi que se calcula al reves: dado el
    valor que el servicio devuelve, cual es el maximo que sigue siendo un buen
    negocio para el municipio.

    fraccion_del_valor es una decision comercial de UDS, no un hecho. El 10% por
    defecto es una convencion prudente, no un resultado del modelo: si UDS cobra
    una decima parte del valor que devuelve, la conversacion con el intendente
    es facil.

    OJO: el costo social no es presupuesto municipal. Este techo dice cuanto
    valor se devuelve, no cuanta plata se ahorra la municipalidad. Presentarlo
    como ahorro fiscal seria mentir.
    """
    return (
        costo.costo_min * fraccion_del_valor,
        costo.costo_central * fraccion_del_valor,
        costo.costo_max * fraccion_del_valor,
    )


def sensibilidad() -> List[tuple]:
    """Cuanto ensancha el resultado cada supuesto, de mayor a menor.

    Es la lista de que medir primero. Hoy el rango de salida es de casi 20x, y
    eso no sirve para vender nada: el numero grande y el chico cuentan historias
    distintas. Pero el modelo si sabe DONDE esta la incertidumbre, y eso convierte
    "no sabemos" en un plan de medicion concreto.

    Devuelve (nombre, cuantas veces ensancha, que habria que hacer para cerrarlo).
    """
    filas = []
    for p, como_cerrarlo in (
        (
            CONSULTAS_MEDICAS_POR_HABITANTE,
            "Pedir al hospital municipal el total de consultas anuales. Un dato "
            "que cualquier director de salud tiene a mano.",
        ),
        (
            HORAS_POR_TURNO_PRESENCIAL,
            "Cronometrar en una visita: cuanto tarda un vecino en sacar un turno. "
            "Media manana de trabajo de campo.",
        ),
        (
            PROPORCION_TURNOS_GESTIONADOS,
            "Preguntar que parte de las consultas son con turno y cuales por guardia.",
        ),
    ):
        if p.tipo is not TipoParametro.SUPUESTO:
            continue
        factor = (p.maximo / p.minimo) if p.minimo else float("inf")
        filas.append((p.nombre, factor, como_cerrarlo))
    return sorted(filas, key=lambda f: f[1], reverse=True)


def advertencias() -> List[str]:
    """Lo que hay que decir SIEMPRE que se muestre este numero."""
    faltantes = [
        p.nombre
        for p in (
            CONSULTAS_MEDICAS_POR_HABITANTE,
            PROPORCION_TURNOS_GESTIONADOS,
            HORAS_POR_TURNO_PRESENCIAL,
        )
        if p.tipo is TipoParametro.SUPUESTO
    ]
    return [
        "ESTIMACION, no dato verificado. Se apoya en supuestos sin fuente: "
        + ", ".join(faltantes),
        "Es COSTO SOCIAL (horas de los vecinos), NO ahorro del presupuesto municipal.",
        "El unico parametro con fuente oficial es el valor hora (SMVM, Resolucion "
        "9/2025). Se eligio el mas bajo defendible, asi que el resultado es un piso.",
        "Solo se calcula sobre municipios con ausencia PROBADA por cita textual.",
    ]


__all__ = [
    "CostoSocial",
    "advertencias",
    "calcular",
    "sensibilidad",
    "techo_de_precio_anual",
]
