"""
Entidades de la capa comercial.

El nombre del archivo importa. `modelos.py` ya existe en src/extraction y
`entidades.py` en src/territorio: con sys.path los modulos homonimos se pisan y
el que carga primero gana. Es la trampa documentada en el handoff, y se volvio a
morder el 2026-08-09 al crear este modulo — llamarlo entidades.py rompio los
tests de Fase 6 sin tocar una linea de Fase 6. De ahi `comercial.py`, que no
existe en ningun otro paquete.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

from pydantic import BaseModel, Field

from catalogo import Area, Friccion


class Oportunidad(BaseModel):
    """Un proceso manual detectado, con la cita que lo prueba.

    NO es un hallazgo de Fase 4 y no vive en la misma base. Un hallazgo dice que
    dice el portal; una oportunidad dice que le falta al municipio y que le
    vende UDS. Mezclarlos contaminaria la base de evidencia con interpretacion
    comercial, y la evidencia es el activo.
    """

    municipio: str
    id_municipio: str
    area: Area
    # El problema en la lengua del intendente, no en la del sistema.
    problema: str
    friccion: Friccion
    # Cita LITERAL de la pagina. Sin esto no hay oportunidad (ADR-0009).
    cita: str
    url: str
    producto: str
    fecha: str
    modelo: Optional[str] = None

    @property
    def id(self) -> str:
        """Determinista: re-correr no duplica filas."""
        semilla = f"{self.id_municipio}|{self.area.value}|{self.cita[:120]}"
        return hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "municipio": self.municipio,
            "id_municipio": self.id_municipio,
            "area": self.area.value,
            "problema": self.problema,
            "friccion": self.friccion.value,
            "cita": self.cita,
            "url": self.url,
            "producto": self.producto,
            "fecha": self.fecha,
            "modelo": self.modelo,
        }


# Peso de cada nivel de friccion para ordenar el trabajo comercial. Una friccion
# alta probada vale mas que tres indicios sueltos, asi que la escala no es lineal.
PESO_FRICCION = {Friccion.ALTA: 5, Friccion.MEDIA: 2, Friccion.BAJA: 1}


class MunicipioOportunidades(BaseModel):
    municipio: str
    id_municipio: str
    fecha: str
    paginas_leidas: int
    caracteres_analizados: int
    oportunidades: List[Oportunidad] = Field(default_factory=list)
    citas_rechazadas: int = 0

    def puntaje(self) -> int:
        """Cuanto hay para vender aca. Ordena los 86."""
        return sum(PESO_FRICCION[o.friccion] for o in self.oportunidades)

    def areas(self) -> List[Area]:
        return sorted({o.area for o in self.oportunidades}, key=lambda a: a.value)


__all__ = ["Oportunidad", "MunicipioOportunidades", "PESO_FRICCION"]
