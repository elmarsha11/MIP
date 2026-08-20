"""
Entidades del rastreo por tema.

El nombre del archivo importa. `modelos.py` ya existe en src/extraction,
`entidades.py` en src/territorio y `comercial.py` en src/oportunidades: con
sys.path los modulos homonimos se pisan y el que carga primero gana. Es la
trampa que ya rompio Fase 6 sin tocar Fase 6. `rastreo.py` no existe en ningun
otro paquete.

Un tema es CONFIGURACION, no codigo. Se declara que se busca (sub-temas,
senales, queries) y el motor hace el resto igual para todos. Agregar un tema
nuevo no deberia costar una linea de logica.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


class TipoEvidencia(str, Enum):
    """De donde salio la cita. No es un detalle: cambia lo que se puede afirmar.

    Una ordenanza prueba que el municipio DECIDIO algo. Una nota de diario
    prueba que algo PASO, que no es lo mismo: un municipio puede aparecer en el
    diario por una jornada de reciclaje sin tener ninguna politica ambiental, y
    otro puede tener un programa por ordenanza del que nadie escribio nunca.

    Por eso viajan separadas hasta el final y la prensa nunca sola confirma.
    """

    OFICIAL = "oficial"  # web municipal, portal, digesto
    NORMATIVA = "normativa"  # ordenanza, decreto, boletin oficial, SIBOM
    PRENSA = "prensa"  # medios locales

    @property
    def es_oficial(self) -> bool:
        return self is not TipoEvidencia.PRENSA


class Estado(str, Enum):
    """Que se puede afirmar de un sub-tema en un municipio.

    ADR-0009: el vacio se registra como vacio. SIN_EVIDENCIA no es un error ni
    un "no", es la respuesta honesta cuando no se encontro nada.
    """

    CONFIRMADO = "confirmado"  # hay cita de fuente oficial o normativa
    INDICIO = "indicio"  # solo prensa: algo pasa, pero no prueba politica
    NO_COMPETE = "no_compete"  # la fuente dice que lo hace otro organismo
    SIN_EVIDENCIA = "sin_evidencia"


class SubTema(BaseModel):
    """Una pregunta concreta dentro de un tema.

    `senales` son las palabras que hacen que una pagina valga la pena leer, y
    las que se usan para cosechar enlaces del portal. No deciden la respuesta:
    eso lo decide el modelo con cita verificada. Mejoran el recall, no fabrican
    el dato.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    pregunta: str = Field(min_length=1)
    # Que tendria que contener la cita para que la respuesta sirva. Va al prompt.
    que_prueba: str = Field(min_length=1)
    senales: Tuple[str, ...] = ()
    # Queries de busqueda para descubrir fuentes que el crawler no encontro.
    queries: Tuple[str, ...] = ()
    # Organismos que NO son el municipio. Si la cita solo habla de estos, la
    # respuesta es NO_COMPETE y no un falso confirmado.
    organismos_ajenos: Tuple[str, ...] = ()
    # True si la pregunta es por algo que YA pasa. Con esto puesto, una cita que
    # solo anuncia una obra futura no confirma nada.
    exige_hecho: bool = False


class Tema(BaseModel):
    """Un tema rastreable, definido enteramente por configuracion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    descripcion: str = ""
    subtemas: Tuple[SubTema, ...]

    def subtema(self, id_subtema: str) -> Optional[SubTema]:
        return next((s for s in self.subtemas if s.id == id_subtema), None)

    @property
    def ids_subtemas(self) -> Tuple[str, ...]:
        return tuple(s.id for s in self.subtemas)

    @property
    def senales(self) -> Tuple[str, ...]:
        vistas: List[str] = []
        for s in self.subtemas:
            for senal in s.senales:
                if senal not in vistas:
                    vistas.append(senal)
        return tuple(vistas)


class HallazgoTema(BaseModel):
    """Una respuesta sobre un sub-tema, con la cita que la prueba.

    No vive en hallazgos_86.sqlite. La evidencia de Fase 4 es el activo y no se
    mezcla con lecturas tematicas, igual que el motor comercial guarda aparte.
    """

    model_config = ConfigDict(extra="forbid")

    municipio: str = Field(min_length=1)
    id_municipio: str = Field(min_length=1)
    tema: str = Field(min_length=1)
    subtema: str = Field(min_length=1)

    estado: Estado
    # Que encontro, en una o dos frases. Es lectura del modelo, no dato duro.
    resumen: str = ""
    # Cita LITERAL de la fuente. Sin esto no hay hallazgo (ADR-0014).
    cita: str = ""
    url: str = ""
    tipo_evidencia: Optional[TipoEvidencia] = None
    fecha: str = ""
    modelo: Optional[str] = None

    @property
    def id(self) -> str:
        crudo = f"{self.id_municipio}|{self.tema}|{self.subtema}|{self.cita[:80]}"
        return hashlib.sha1(crudo.encode("utf-8")).hexdigest()[:16]

    @property
    def prueba_politica(self) -> bool:
        """True si la cita sostiene que el municipio tiene politica, no solo que algo paso."""
        return self.estado is Estado.CONFIRMADO


class MunicipioTema(BaseModel):
    """Lo que se sabe de un municipio sobre un tema."""

    model_config = ConfigDict(extra="forbid")

    municipio: str = Field(min_length=1)
    id_municipio: str = Field(min_length=1)
    tema: str = Field(min_length=1)
    hallazgos: List[HallazgoTema] = Field(default_factory=list)
    paginas_leidas: int = 0
    error: Optional[str] = None

    def por_subtema(self, id_subtema: str) -> List[HallazgoTema]:
        return [h for h in self.hallazgos if h.subtema == id_subtema]

    def estado_de(self, id_subtema: str) -> Estado:
        """El mejor estado alcanzado para un sub-tema.

        Confirmado gana a indicio, e indicio gana a no_compete: si una ordenanza
        prueba el programa, que ademas haya salido en el diario no lo degrada.
        """
        orden = {
            Estado.CONFIRMADO: 3,
            Estado.INDICIO: 2,
            Estado.NO_COMPETE: 1,
            Estado.SIN_EVIDENCIA: 0,
        }
        estados = [h.estado for h in self.por_subtema(id_subtema)]
        if not estados:
            return Estado.SIN_EVIDENCIA
        return max(estados, key=lambda e: orden[e])


__all__ = [
    "Estado",
    "HallazgoTema",
    "MunicipioTema",
    "SubTema",
    "Tema",
    "TipoEvidencia",
]
