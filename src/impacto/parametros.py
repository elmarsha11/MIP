"""
Fase 5 - Parametros del modelo de impacto.

Cada numero que entra a un calculo de MIP es un Parametro con fuente, fecha y
confianza. No hay constantes sueltas en el codigo.

Esto existe por la constante de $31.001 por habitante, que arrastraba todo el
calculo de impacto de $32.743M y tenia R^2 = 1,0 contra poblacion x brecha. Un
R^2 perfecto no es un hallazgo: es la firma de una formula mecanica sin fuente
externa. ADR-0009 la mando a cuarentena y este modulo es su reemplazo.

Regla: un parametro sin fuente verificable NO se puede usar para afirmar. Se
declara como supuesto, con rango, y el resultado sale como rango y con la
leyenda de que es un supuesto. Nunca como un numero unico y limpio.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TipoParametro(str, Enum):
    """De donde sale el numero. Define que se puede afirmar con el."""

    OFICIAL = "oficial"  # publicado por un organismo, con norma citable
    ESTADISTICA = "estadistica"  # relevamiento publico verificable
    MEDIDO_POR_MIP = "medido_por_mip"  # sale de la propia base, con evidencia
    SUPUESTO = "supuesto"  # no hay fuente: se declara y se le pone rango
    DEFINIDO_POR_UDS = "definido_por_uds"  # decision comercial, no un hecho


class Parametro(BaseModel):
    """Un numero con su procedencia."""

    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1)
    valor: Optional[float] = None
    unidad: str = Field(min_length=1)
    tipo: TipoParametro
    fuente: Optional[str] = None
    fecha_fuente: Optional[str] = None
    nota: Optional[str] = None
    # Para supuestos: el rango en el que se mueve, para analisis de sensibilidad.
    minimo: Optional[float] = None
    maximo: Optional[float] = None

    @model_validator(mode="after")
    def _reglas(self) -> "Parametro":
        if self.tipo in (TipoParametro.OFICIAL, TipoParametro.ESTADISTICA):
            if not self.fuente or not self.fecha_fuente:
                raise ValueError(
                    f"'{self.nombre}' se declara {self.tipo.value} pero no trae fuente "
                    f"y fecha. Un numero sin procedencia no puede afirmar nada (ADR-0009)."
                )
        if self.tipo is TipoParametro.SUPUESTO:
            if self.minimo is None or self.maximo is None:
                raise ValueError(
                    f"'{self.nombre}' es un supuesto y necesita minimo y maximo. "
                    f"Un supuesto sin rango se lee como si fuera un dato."
                )
            if self.minimo > self.maximo:
                raise ValueError(f"'{self.nombre}': minimo mayor que maximo")
        return self

    @property
    def es_afirmable(self) -> bool:
        """True si el parametro puede sostener una afirmacion, no solo una estimacion."""
        return self.tipo in (
            TipoParametro.OFICIAL,
            TipoParametro.ESTADISTICA,
            TipoParametro.MEDIDO_POR_MIP,
        ) and self.valor is not None

    def rango(self) -> tuple:
        """(minimo, valor, maximo). Para los afirmables los tres coinciden."""
        if self.tipo is TipoParametro.SUPUESTO:
            centro = self.valor if self.valor is not None else (self.minimo + self.maximo) / 2
            return (self.minimo, centro, self.maximo)
        return (self.valor, self.valor, self.valor)

    def citar(self) -> str:
        if self.tipo is TipoParametro.SUPUESTO:
            return f"SUPUESTO, sin fuente. Rango usado: {self.minimo}-{self.maximo} {self.unidad}"
        if self.tipo is TipoParametro.DEFINIDO_POR_UDS:
            return "Definido por UDS (decision comercial, no un hecho verificable)"
        return f"{self.fuente} ({self.fecha_fuente})"


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------

VALOR_HORA_VECINO = Parametro(
    nombre="valor_hora_vecino",
    valor=1883.0,
    unidad="ARS/hora",
    tipo=TipoParametro.OFICIAL,
    fuente=(
        "Salario Minimo Vital y Movil, Resolucion 9/2025 del Consejo Nacional del "
        "Empleo, la Productividad y el SMVM. Boletin Oficial 3/12/2025. "
        "Valor vigente agosto 2026: $376.600 mensual, $1.883 por hora."
    ),
    fecha_fuente="2026-08",
    nota=(
        "Se elige el SMVM y no el salario promedio a proposito. Es el valor mas bajo "
        "defendible, asi que todo lo que se calcule con el es un PISO, no una "
        "estimacion. Frente a un auditor no hay que defender el numero: hay que "
        "mostrar la resolucion. Usar el salario promedio daria cifras mas grandes y "
        "mas faciles de refutar."
    ),
)

# --- lo que todavia no tiene fuente ---------------------------------------
# Se declaran como supuestos con rango explicito. El modelo los usa para dar un
# rango, nunca un numero unico, y lo dice en la salida.

HORAS_POR_TURNO_PRESENCIAL = Parametro(
    nombre="horas_por_turno_presencial",
    unidad="horas por turno",
    tipo=TipoParametro.SUPUESTO,
    minimo=1.0,
    maximo=4.0,
    valor=2.0,
    nota=(
        "Horas que pierde un vecino para sacar un turno yendo o llamando: viaje, "
        "espera y tramite. Rango conservador. Para cerrarlo hace falta medicion en "
        "un municipio real, que es algo que UDS puede hacer en la primera visita."
    ),
)

CONSULTAS_MEDICAS_POR_HABITANTE = Parametro(
    nombre="consultas_medicas_por_habitante_anuales",
    unidad="consultas por habitante por ano",
    tipo=TipoParametro.SUPUESTO,
    minimo=1.5,
    maximo=3.5,
    valor=2.0,
    nota=(
        "Consultas al sistema publico municipal por habitante y por ano. NO tiene "
        "fuente verificada todavia. Hay estadisticas nacionales de consultas medicas, "
        "pero mezclan publico y privado y no discriminan por municipio. Pendiente de "
        "una fuente citable antes de usar este modelo en una propuesta comercial."
    ),
)

PROPORCION_TURNOS_GESTIONADOS = Parametro(
    nombre="proporcion_consultas_que_requieren_pedir_turno",
    unidad="proporcion",
    tipo=TipoParametro.SUPUESTO,
    minimo=0.4,
    maximo=0.8,
    valor=0.6,
    nota=(
        "Parte de las consultas que exigen gestionar un turno por separado. Las "
        "guardias y urgencias no lo requieren."
    ),
)

CATALOGO = {
    p.nombre: p
    for p in (
        VALOR_HORA_VECINO,
        HORAS_POR_TURNO_PRESENCIAL,
        CONSULTAS_MEDICAS_POR_HABITANTE,
        PROPORCION_TURNOS_GESTIONADOS,
    )
}


def parametros_sin_fuente() -> list:
    """Los que hoy impiden afirmar. Es la lista de tareas de investigacion.

    ADR-0009: un dato faltante genera una tarea, no un numero inventado.
    """
    return [p for p in CATALOGO.values() if p.tipo is TipoParametro.SUPUESTO]


__all__ = [
    "CATALOGO",
    "CONSULTAS_MEDICAS_POR_HABITANTE",
    "HORAS_POR_TURNO_PRESENCIAL",
    "PROPORCION_TURNOS_GESTIONADOS",
    "VALOR_HORA_VECINO",
    "Parametro",
    "TipoParametro",
    "parametros_sin_fuente",
]
