"""
Modelos de Fase 4 - Extraccion con los 5 sellos.

Contrato: ADR-0014 (la IA propone, el codigo verifica), ADR-0009 (sin evidencia
no hay dato), schemas/diccionario_datos_oficial_v1.md.

Los 5 sellos del Capitulo 7 son campos obligatorios del modelo, no una
convencion: url + fecha + fragmento literal + tipo de fuente + confianza. Si
falta uno, el hallazgo no se construye.
"""

from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Variables del diccionario
# ---------------------------------------------------------------------------


class Variable(str, Enum):
    """Que mide MIP. Cruza el Gold Standard con las 7 variables de UDS."""

    TRAMITES_ONLINE = "tramites_online"
    TURNOS_SALUD_ONLINE = "turnos_salud_online"
    PAGO_ONLINE_TASAS = "pago_online_tasas"
    SISTEMA_RAFAM = "sistema_rafam"
    EXPEDIENTE_DIGITAL_GDE = "expediente_digital_gde"
    RECLAMOS_147 = "reclamos_147"
    TRANSPARENCIA_PRESUPUESTO = "transparencia_presupuesto"
    BOLETIN_OFICIAL = "boletin_oficial"
    LICITACIONES = "licitaciones"
    APP_MUNICIPAL = "app_municipal"


class Valor(str, Enum):
    """Respuesta admitida para una variable binaria.

    NO_VERIFICABLE es una respuesta de primera clase, no un error. ADR-0009: el
    vacio se registra como vacio. El ETL previo forzaba booleanos obligatorios y
    por eso fabricaba datos.
    """

    SI = "si"
    NO = "no"
    NO_VERIFICABLE = "no_verificable"


class TipoFuente(str, Enum):
    PORTAL_OFICIAL = "portal_oficial"
    REGISTRO_PROVINCIAL = "registro_provincial"
    RED_SOCIAL = "red_social"
    STORE_APP = "store_app"
    OTRO = "otro"


class Confianza(str, Enum):
    ALTA = "Alta"
    MEDIA = "Media"
    BAJA = "Baja"
    CERO = "0%"


class EstadoHallazgo(str, Enum):
    VERIFICADO = "verificado"  # la cita existe literal en la fuente
    NO_VERIFICABLE = "no_verificable"  # el texto no alcanza para afirmar nada
    CITA_RECHAZADA = "cita_rechazada"  # el modelo cito algo que no esta en la fuente


# ---------------------------------------------------------------------------
# Verificacion de citas
# ---------------------------------------------------------------------------


def normalizar_para_cotejo(texto: str) -> str:
    """Normaliza para comparar cita contra fuente.

    Tolera diferencias de espaciado, mayusculas y comillas tipograficas, que el
    modelo cambia sin alterar el contenido. No tolera palabras distintas: ahi
    esta el limite entre citar y parafrasear.
    """
    t = texto.lower()
    t = t.replace("“", '"').replace("”", '"').replace("’", "'")
    t = t.replace("‘", "'").replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def cita_esta_en_fuente(cita: str, fuente: str, minimo_caracteres: int = 12) -> bool:
    """True si la cita aparece literalmente en el texto que se le dio al modelo.

    Es el corazon de ADR-0014. Una cita demasiado corta no prueba nada (cualquier
    texto contiene "salud"), asi que se exige un minimo.
    """
    if not cita or not fuente:
        return False
    limpia = normalizar_para_cotejo(cita)
    if len(limpia) < minimo_caracteres:
        return False
    return limpia in normalizar_para_cotejo(fuente)


# ---------------------------------------------------------------------------
# Hallazgo
# ---------------------------------------------------------------------------


class Hallazgo(BaseModel):
    """Un dato sobre un municipio, con sus 5 sellos."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    municipio: str = Field(min_length=1)
    id_municipio: str = Field(min_length=1)
    variable: Variable

    valor: str = Field(min_length=1)
    detalle: Optional[str] = None  # lista de tramites, nombre de la app, etc.

    # -- los 5 sellos ------------------------------------------------------
    url: Optional[str] = None
    fecha: str = Field(min_length=1)
    fragmento: Optional[str] = None
    tipo_fuente: Optional[TipoFuente] = None
    confianza: Confianza

    # -- trazabilidad del paso de IA ---------------------------------------
    estado: EstadoHallazgo
    modelo: Optional[str] = None

    @model_validator(mode="after")
    def _asignar_id(self) -> "Hallazgo":
        if not self.id:
            semilla = f"{self.id_municipio}|{self.variable.value}"
            object.__setattr__(
                self, "id", "hal_" + hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:12]
            )
        return self

    @field_validator("fragmento")
    @classmethod
    def _fragmento_vacio_es_none(cls, v: Optional[str]) -> Optional[str]:
        return (v or "").strip() or None

    @model_validator(mode="after")
    def _adr_0009_sin_evidencia_no_hay_dato(self) -> "Hallazgo":
        """Sin fragmento verificado, el hallazgo no puede afirmar nada."""
        if self.estado is EstadoHallazgo.VERIFICADO:
            if not self.fragmento:
                raise ValueError(
                    f"ADR-0014: un hallazgo verificado necesita fragmento literal. "
                    f"{self.municipio}/{self.variable.value}"
                )
            if not self.url:
                raise ValueError(
                    f"ADR-0009: los 5 sellos exigen URL. "
                    f"{self.municipio}/{self.variable.value}"
                )
            return self

        # No verificado: no puede afirmar si/no ni tener confianza util.
        if self.valor not in (Valor.NO_VERIFICABLE.value, ""):
            raise ValueError(
                f"ADR-0009: {self.municipio}/{self.variable.value} no esta verificado, "
                f"asi que su valor solo puede ser 'no_verificable', no {self.valor!r}"
            )
        if self.confianza not in (Confianza.BAJA, Confianza.CERO):
            raise ValueError(
                f"ADR-0009: un hallazgo sin verificar no puede tener confianza "
                f"{self.confianza.value!r}"
            )
        return self

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "municipio": self.municipio,
            "id_municipio": self.id_municipio,
            "variable": self.variable.value,
            "valor": self.valor,
            "detalle": self.detalle,
            "url": self.url,
            "fecha": self.fecha,
            "fragmento": self.fragmento,
            "tipo_fuente": self.tipo_fuente.value if self.tipo_fuente else None,
            "confianza": self.confianza.value,
            "estado": self.estado.value,
            "modelo": self.modelo,
        }


class MunicipioExtraccion(BaseModel):
    """Todos los hallazgos de un municipio."""

    model_config = ConfigDict(extra="forbid")

    municipio: str = Field(min_length=1)
    id_municipio: str = Field(min_length=1)
    fecha: str
    paginas_leidas: int = 0
    caracteres_analizados: int = 0
    llamadas_ia: int = 0
    hallazgos: List[Hallazgo] = Field(default_factory=list)

    def verificados(self) -> List[Hallazgo]:
        return [h for h in self.hallazgos if h.estado is EstadoHallazgo.VERIFICADO]

    def por_variable(self, variable: Variable) -> Optional[Hallazgo]:
        for h in self.hallazgos:
            if h.variable is variable:
                return h
        return None

    def rechazados(self) -> List[Hallazgo]:
        """Citas que el modelo invento y la verificacion tumbo. Vale medirlas:
        es el termometro de cuanto alucina el modelo que estamos usando."""
        return [h for h in self.hallazgos if h.estado is EstadoHallazgo.CITA_RECHAZADA]


__all__ = [
    "Confianza",
    "EstadoHallazgo",
    "Hallazgo",
    "MunicipioExtraccion",
    "TipoFuente",
    "Valor",
    "Variable",
    "cita_esta_en_fuente",
    "normalizar_para_cotejo",
]
