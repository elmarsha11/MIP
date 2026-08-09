"""
Fase 6 - Censo territorial: las entidades de un municipio.

Hasta aca MIP medía VARIABLES del municipio: tiene turnos online si o no, publica
licitaciones si o no. Eso responde "como esta el municipio".

Esto responde otra cosa: "que hay adentro del municipio". Un hospital no es un
si/no, es una entidad con nombre, direccion y coordenadas. Lo mismo una escuela,
un barrio, una plaza o un destacamento policial.

Es el zoom de un mapa: de los 86 municipios a la puerta de un CAPS.

Regla de siempre (ADR-0009): cada entidad viaja con su fuente y su identificador
en el origen, para poder volver a mirarla. Una entidad sin procedencia no entra.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TipoEntidad(str, Enum):
    """Que puede haber adentro de un municipio.

    Cerrado a proposito, igual que el enum de tipos de URL: sin un vocabulario
    comun, 86 municipios producen 86 taxonomias distintas y nada es comparable.
    """

    # Salud
    HOSPITAL = "hospital"
    CAPS = "caps"  # centro de atencion primaria
    CLINICA_PRIVADA = "clinica_privada"
    FARMACIA = "farmacia"
    # Educacion
    JARDIN = "jardin"
    ESCUELA_PRIMARIA = "escuela_primaria"
    ESCUELA_SECUNDARIA = "escuela_secundaria"
    ESCUELA_ESPECIAL = "escuela_especial"
    EDUCACION_SUPERIOR = "educacion_superior"
    ESCUELA_SIN_CLASIFICAR = "escuela_sin_clasificar"
    # Gobierno y seguridad
    MUNICIPALIDAD = "municipalidad"
    DELEGACION = "delegacion"
    CONCEJO_DELIBERANTE = "concejo_deliberante"
    POLICIA = "policia"
    BOMBEROS = "bomberos"
    # Territorio
    BARRIO = "barrio"
    LOCALIDAD = "localidad"
    # Cultura, deporte y comunidad
    BIBLIOTECA = "biblioteca"
    TEATRO = "teatro"
    MUSEO = "museo"
    CENTRO_COMUNITARIO = "centro_comunitario"
    CLUB_DEPORTIVO = "club_deportivo"
    PLAZA = "plaza"
    # Otros servicios
    OTRO = "otro"


# Que agrupacion mostrar en el tablero. Un municipio no se lee entidad por
# entidad: se lee por capas, como un mapa.
CAPAS = {
    "Salud": (
        TipoEntidad.HOSPITAL, TipoEntidad.CAPS, TipoEntidad.CLINICA_PRIVADA,
        TipoEntidad.FARMACIA,
    ),
    "Educación": (
        TipoEntidad.JARDIN, TipoEntidad.ESCUELA_PRIMARIA, TipoEntidad.ESCUELA_SECUNDARIA,
        TipoEntidad.ESCUELA_ESPECIAL, TipoEntidad.EDUCACION_SUPERIOR,
        TipoEntidad.ESCUELA_SIN_CLASIFICAR,
    ),
    "Gobierno y seguridad": (
        TipoEntidad.MUNICIPALIDAD, TipoEntidad.DELEGACION, TipoEntidad.CONCEJO_DELIBERANTE,
        TipoEntidad.POLICIA, TipoEntidad.BOMBEROS,
    ),
    "Territorio": (TipoEntidad.BARRIO, TipoEntidad.LOCALIDAD),
    "Cultura y comunidad": (
        TipoEntidad.BIBLIOTECA, TipoEntidad.TEATRO, TipoEntidad.MUSEO,
        TipoEntidad.CENTRO_COMUNITARIO, TipoEntidad.CLUB_DEPORTIVO, TipoEntidad.PLAZA,
    ),
}


# Tipos donde una entidad sin nombre no aporta nada. En Chascomus, OSM tiene 226
# leisure=park y la mayoria son poligonos de "equipamiento comunitario" sin
# nombre, importados en bloque: ahogaban al resto del censo. Una plaza que no se
# puede nombrar no se puede visitar ni citar en un informe.
#
# En salud, educacion y gobierno se conservan aunque no tengan nombre: un CAPS
# sin rotular sigue siendo un CAPS que existe y que hay que ir a ver.
REQUIEREN_NOMBRE = frozenset({
    TipoEntidad.PLAZA,
    TipoEntidad.OTRO,
    TipoEntidad.CLUB_DEPORTIVO,
})


class FuenteEntidad(str, Enum):
    OSM = "openstreetmap"
    PORTAL_MUNICIPAL = "portal_municipal"
    REGISTRO_PROVINCIAL = "registro_provincial"
    CARGA_MANUAL = "carga_manual"


class Entidad(BaseModel):
    """Una cosa que existe adentro del municipio, con su procedencia."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    municipio: str = Field(min_length=1)
    id_municipio: str = Field(min_length=1)

    tipo: TipoEntidad
    nombre: Optional[str] = None

    latitud: Optional[float] = None
    longitud: Optional[float] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    web: Optional[str] = None
    operador: Optional[str] = None  # municipal, provincial, privado...

    # -- procedencia -------------------------------------------------------
    fuente: FuenteEntidad
    id_en_fuente: str = Field(min_length=1)  # ej: node/123456789
    url_fuente: Optional[str] = None
    fecha: str = Field(min_length=1)
    etiquetas_crudas: Optional[dict] = None  # lo que dijo el origen, sin interpretar

    @model_validator(mode="after")
    def _asignar_id(self) -> "Entidad":
        if not self.id:
            semilla = f"{self.fuente.value}|{self.id_en_fuente}"
            object.__setattr__(
                self, "id", "ent_" + hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:12]
            )
        return self

    @model_validator(mode="after")
    def _coordenadas_validas(self) -> "Entidad":
        """Argentina continental. Una coordenada fuera de rango es un error de
        importacion, no un dato: mejor que falle a que quede un hospital en Asia."""
        if self.latitud is not None:
            if not (-56.0 <= self.latitud <= -21.0):
                raise ValueError(f"latitud fuera de Argentina: {self.latitud}")
        if self.longitud is not None:
            if not (-74.0 <= self.longitud <= -53.0):
                raise ValueError(f"longitud fuera de Argentina: {self.longitud}")
        return self

    @property
    def ubicada(self) -> bool:
        return self.latitud is not None and self.longitud is not None

    def to_row(self) -> dict:
        import json as _json

        return {
            "id": self.id,
            "municipio": self.municipio,
            "id_municipio": self.id_municipio,
            "tipo": self.tipo.value,
            "nombre": self.nombre,
            "latitud": self.latitud,
            "longitud": self.longitud,
            "direccion": self.direccion,
            "telefono": self.telefono,
            "web": self.web,
            "operador": self.operador,
            "fuente": self.fuente.value,
            "id_en_fuente": self.id_en_fuente,
            "url_fuente": self.url_fuente,
            "fecha": self.fecha,
            "etiquetas_crudas": _json.dumps(self.etiquetas_crudas, ensure_ascii=False)
            if self.etiquetas_crudas
            else None,
        }


class CensoMunicipio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    municipio: str = Field(min_length=1)
    id_municipio: str = Field(min_length=1)
    osm_id: Optional[int] = None
    fecha: str
    entidades: List[Entidad] = Field(default_factory=list)

    def por_tipo(self, tipo: TipoEntidad) -> List[Entidad]:
        return [e for e in self.entidades if e.tipo is tipo]

    def por_capa(self) -> dict:
        salida = {}
        for capa, tipos in CAPAS.items():
            conjunto = set(tipos)
            elegidas = [e for e in self.entidades if e.tipo in conjunto]
            if elegidas:
                salida[capa] = elegidas
        return salida

    def resumen(self) -> dict:
        from collections import Counter

        cuenta = Counter(e.tipo.value for e in self.entidades)
        return {
            "total": len(self.entidades),
            "ubicadas": len([e for e in self.entidades if e.ubicada]),
            "con_nombre": len([e for e in self.entidades if e.nombre]),
            "por_tipo": dict(cuenta.most_common()),
        }


__all__ = [
    "CAPAS",
    "CensoMunicipio",
    "Entidad",
    "FuenteEntidad",
    "TipoEntidad",
]
