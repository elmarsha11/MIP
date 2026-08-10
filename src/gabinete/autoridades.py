"""
Entidades de la cupula municipal.

El archivo NO se llama modelos.py ni entidades.py ni comercial.py: los tres ya
existen en otros paquetes y con sys.path se pisan. Es la trampa del handoff, que
se volvio a morder el 2026-08-09 al crear src/oportunidades.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Cargo(str, Enum):
    INTENDENTE = "intendente"
    SECRETARIO = "secretario"


class TipoFuente(str, Enum):
    """De donde salio, en orden de dureza. Ordena la confianza."""

    BOLETIN_OFICIAL = "boletin_oficial"   # decreto publicado, con fecha
    PORTAL = "portal"                     # sitio oficial del municipio
    RED_OFICIAL = "red_oficial"           # Instagram/Facebook del municipio


# Un decreto que nombra a quien lo refrenda es prueba dura. El portal es oficial
# pero puede tener una nota vieja sin fecha visible. La red oficial es del
# municipio, pero es lo mas volatil y lo mas dificil de fechar.
CONFIANZA = {
    TipoFuente.BOLETIN_OFICIAL: "Alta",
    TipoFuente.PORTAL: "Media",
    TipoFuente.RED_OFICIAL: "Baja",
}


class Autoridad(BaseModel):
    municipio: str
    id_municipio: str
    cargo: Cargo
    # Vacio para el intendente; para un secretario, el area ("Gobierno",
    # "Hacienda", "Obras, Servicios Publicos y Ambiente").
    area: Optional[str] = None
    nombre: str
    cita: str
    url: str
    fuente: TipoFuente
    # Cuando se corrio el analisis. NO sirve para saber si el dato sigue vigente.
    fecha: str
    # Fecha del DECRETO que lo prueba, en ISO. Es la que importa: un gabinete
    # cambia, y sin esto la base no distingue "es" de "fue". Paso con Chascomus:
    # Jorge Marino firmo como Secretario de Obras hasta abril de 2026 y Lucas
    # Funes desde mayo. Los dos aparecen en el boletin y las dos citas son
    # literales; lo unico que los ordena es la fecha de la norma.
    fecha_norma: Optional[str] = None
    modelo: Optional[str] = None

    @property
    def confianza(self) -> str:
        return CONFIANZA[self.fuente]

    @property
    def id(self) -> str:
        """Determinista: re-correr no duplica filas.

        Incluye la FUENTE a proposito. Si no, el boletin y el portal colisionan y
        el segundo pisa al primero en silencio — justo cuando se contradicen, que
        es cuando mas importa verlos a los dos.

        El caso que lo justifica, con desenlace: en Chascomus el decreto nombra a
        Lucas Funes en Obras desde mayo de 2026, mientras los diarios locales
        seguian dando a Jorge Marino. Juli reviso y confirmo que el actual es
        Funes: el boletin tenia razon y la prensa estaba atrasada. Lo que
        disparo esa revision fue ver la contradiccion, no resolverla sola.
        """
        semilla = (
            f"{self.id_municipio}|{self.cargo.value}|{(self.area or '').lower()}"
            f"|{self.fuente.value}"
        )
        return hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "municipio": self.municipio,
            "id_municipio": self.id_municipio,
            "cargo": self.cargo.value,
            "area": self.area,
            "nombre": self.nombre,
            "cita": self.cita,
            "url": self.url,
            "fuente": self.fuente.value,
            "confianza": self.confianza,
            "fecha": self.fecha,
            "fecha_norma": self.fecha_norma,
            "modelo": self.modelo,
        }


class MunicipioGabinete(BaseModel):
    municipio: str
    id_municipio: str
    fecha: str
    boletines_leidos: int = 0
    caracteres_analizados: int = 0
    autoridades: List[Autoridad] = Field(default_factory=list)
    rechazadas: int = 0

    def intendente(self) -> Optional[Autoridad]:
        return next((a for a in self.autoridades if a.cargo is Cargo.INTENDENTE), None)

    def secretarios(self) -> List[Autoridad]:
        return [a for a in self.autoridades if a.cargo is Cargo.SECRETARIO]


__all__ = ["Autoridad", "Cargo", "CONFIANZA", "MunicipioGabinete", "TipoFuente"]
