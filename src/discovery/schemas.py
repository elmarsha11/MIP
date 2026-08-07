"""
Modelos Pydantic de Fase 3 - Descubrimiento.

Contrato: schemas/discovery_schema.md
Reglas duras: decisions/ADR-0009 (no ocultar vacios) y ADR-0010 (max 20 URLs, sin fragmento no hay URL).

Las reglas de ADR-0009/0010 se implementan como validadores que LEVANTAN ValidationError.
No se degradan silenciosamente: si el motor intenta guardar una URL sin evidencia con
confianza Alta, el proceso falla. Es intencional: preferimos romper el pipeline antes que
publicar un dato inventado.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Limites del contrato
# ---------------------------------------------------------------------------

# ADR-0010: 20 URLs por municipio es MAXIMO, no minimo. Si solo hay 8 reales, se guardan 8.
MAX_URLS_POR_MUNICIPIO = 20


# ---------------------------------------------------------------------------
# Enums cerrados
# ---------------------------------------------------------------------------


class TipoURL(str, Enum):
    """Enum cerrado de schemas/discovery_schema.md (seccion 'Enum tipo').

    Nota: docs/Fase3_Plan_Descubrimiento.md lista variantes de nombre
    (hacienda_tasas, boletin_oficial, normativa). Manda el schema.
    """

    SITIO_OFICIAL = "sitio_oficial"
    TRAMITES = "tramites"
    TRANSPARENCIA = "transparencia"
    BOLETIN_SIBOM = "boletin_sibom"
    SALUD_TURNOS = "salud_turnos"
    HACIENDA_TASAS_RAFAM = "hacienda_tasas_rafam"
    RECLAMOS_147 = "reclamos_147"
    GDE_EXPEDIENTE = "gde_expediente"
    FACEBOOK_OFICIAL = "facebook_oficial"
    INSTAGRAM_OFICIAL = "instagram_oficial"
    YOUTUBE_OFICIAL = "youtube_oficial"
    PLAY_STORE = "play_store"
    APP_STORE = "app_store"
    NORMATIVA_ORDENANZAS = "normativa_ordenanzas"
    LICITACIONES = "licitaciones"
    OTRO = "otro"


class Confianza(str, Enum):
    """Valores admitidos por el CHECK de la tabla discovery_urls."""

    ALTA = "Alta"
    MEDIA = "Media"
    BAJA = "Baja"
    CERO = "0%"  # ADR-0009: no investigado / no verificable, NO es 0 numerico


class EstadoValidacion(str, Enum):
    """schemas/discovery_schema.md nombra validada/pendiente/error_404.

    Se agregan no_verificable y no_encontrado porque ADR-0009 y ADR-0010 los exigen
    explicitamente ("se guarda como No Encontrado, no se fabrica" / "sin fragmento
    estado = No Verificable"). La columna SQLite es TEXT sin CHECK, asi que no rompe
    el contrato de la tabla.
    """

    PENDIENTE = "pendiente"
    VALIDADA = "validada"
    NO_VERIFICABLE = "no_verificable"
    NO_ENCONTRADO = "no_encontrado"
    ERROR_404 = "error_404"


# Estados en los que una URL todavia no tiene evidencia y por lo tanto no puede
# afirmar nada (ADR-0009).
ESTADOS_SIN_EVIDENCIA = frozenset(
    {EstadoValidacion.NO_VERIFICABLE, EstadoValidacion.NO_ENCONTRADO}
)


# ---------------------------------------------------------------------------
# Utilidades de texto (compartidas con heuristics.py y validator.py)
# ---------------------------------------------------------------------------


def quitar_acentos(texto: str) -> str:
    """Descompone y elimina diacriticos. 'Chascomús' -> 'Chascomus'."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_slug(nombre: str) -> str:
    """Nombre de municipio -> slug de dominio.

    'Coronel Suárez'      -> 'coronelsuarez'
    'Saavedra (Pigüé)'    -> 'saavedra'      (se descarta el parentetico)
    '9 de Julio'          -> '9dejulio'
    'San Andrés de Giles' -> 'sanandresdegiles'
    """
    base = re.sub(r"\(.*?\)", " ", nombre)  # fuera parenteticos
    base = quitar_acentos(base).lower()
    return re.sub(r"[^a-z0-9]", "", base)


# Muchos municipios se conocen por el nombre corto y su dominio lo refleja:
# General Madariaga -> madariaga.gob.ar, San Antonio de Areco -> areco.ar.
PREFIJOS_OMITIBLES = (
    "general ", "coronel ", "villa ", "san miguel del ", "san antonio de ",
    "presidente ", "doctor ", "leandro n. ", "adolfo ", "florentino ",
    "hipolito ", "benito ", "carlos ", "roque ", "capitan ", "gonzales ",
)


def variantes_slug(municipio: str) -> List[str]:
    """Slugs plausibles del municipio, del mas fiel al mas corto.

    'General Madariaga'    -> ['generalmadariaga', 'madariaga']
    'San Antonio de Areco' -> ['sanantoniodeareco', 'areco']

    Lo usan el descubridor de dominios (para adivinar) y el validador (para
    decidir si una URL apunta al municipio).
    """
    variantes = [normalizar_slug(municipio)]
    minuscula = quitar_acentos(municipio).lower()
    for prefijo in PREFIJOS_OMITIBLES:
        if minuscula.startswith(prefijo):
            corto = normalizar_slug(municipio[len(prefijo):])
            if corto and corto not in variantes:
                variantes.append(corto)
    return variantes


def normalizar_texto(texto: str) -> str:
    """Normaliza para comparar: sin acentos, minusculas, espacios colapsados."""
    return re.sub(r"\s+", " ", quitar_acentos(texto).lower()).strip()


def ahora_iso() -> str:
    """Timestamp ISO8601 UTC con sufijo Z, como pide el schema."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def es_https(url: str) -> bool:
    """False = el sitio no ofrece TLS. Es un hallazgo de madurez digital, no un error."""
    return url.strip().lower().startswith("https://")


def generar_id(municipio: str, url: str) -> str:
    """ID deterministico a partir de (municipio, url).

    El schema dice 'UUID' con ejemplo 'dis_001'. Usamos un hash estable en vez de
    uuid4 para que re-correr el motor sobre el mismo municipio no genere filas
    nuevas: la UNIQUE(municipio, url) de la tabla queda alineada con el PRIMARY KEY.
    """
    semilla = f"{normalizar_texto(municipio)}|{url.strip().lower()}"
    return "dis_" + hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Modelo de URL descubierta
# ---------------------------------------------------------------------------


class DiscoveryURL(BaseModel):
    """Una fila de la tabla discovery_urls."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    id: str = ""
    municipio: str = Field(min_length=1)
    id_municipio: str = Field(min_length=1)
    url: str = Field(min_length=1)
    tipo: TipoURL
    fuente_query: str = Field(min_length=1)
    titulo_fragmento: Optional[str] = None
    fecha_descubrimiento: str = Field(default_factory=ahora_iso)
    confianza: Confianza
    estado_validacion: EstadoValidacion
    # None = todavia no se sabe. ADR-0009: desconocido no es False.
    es_oficial: Optional[bool] = None

    # -- normalizacion ------------------------------------------------------

    @field_validator("url")
    @classmethod
    def _url_absoluta(cls, v: str) -> str:
        """La URL debe ser absoluta. Se prefiere https, se admite http.

        schemas/discovery_schema.md pide https://. Se relaja a http:// porque hay
        municipios cuyo sitio oficial solo existe sin TLS (Rauch, Villarino,
        verificado el 2026-08-07): exigir https los borraria del relevamiento.
        Que un municipio no tenga HTTPS no es un problema del dato, es el dato.
        Ver ADR-0012.
        """
        v = v.strip()
        for esquema in ("https://", "http://"):
            if v.startswith(esquema):
                if len(v) <= len(esquema):
                    raise ValueError(f"URL sin host: {v!r}")
                return v
        raise ValueError(
            f"schemas/discovery_schema.md: la URL debe ser absoluta con "
            f"https:// (o http:// si el municipio no tiene TLS) -> {v!r}"
        )

    @field_validator("titulo_fragmento")
    @classmethod
    def _fragmento_vacio_es_none(cls, v: Optional[str]) -> Optional[str]:
        """'' y '   ' se guardan como None. No existe el fragmento vacio."""
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("fecha_descubrimiento")
    @classmethod
    def _fecha_iso8601(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"fecha_descubrimiento debe ser ISO8601: {v!r}") from exc
        return v

    # -- reglas de negocio --------------------------------------------------

    @model_validator(mode="after")
    def _asignar_id(self) -> "DiscoveryURL":
        if not self.id:
            object.__setattr__(self, "id", generar_id(self.municipio, self.url))
        return self

    @model_validator(mode="after")
    def _adr_0009_sin_fragmento_no_hay_dato(self) -> "DiscoveryURL":
        """ADR-0009 / ADR-0010: sin fragmento no hay URL valida.

        Una URL sin evidencia textual puede existir como CANDIDATA, pero solo con
        confianza Baja (o 0%) y estado no_verificable / no_encontrado. Nunca puede
        afirmar Alta ni Media, ni declararse validada.
        """
        if self.titulo_fragmento is not None:
            return self

        if self.confianza not in (Confianza.BAJA, Confianza.CERO):
            raise ValueError(
                f"ADR-0009: URL sin titulo_fragmento no puede tener confianza "
                f"{self.confianza.value!r}. Permitido: Baja o 0%. url={self.url}"
            )
        if self.estado_validacion not in ESTADOS_SIN_EVIDENCIA:
            raise ValueError(
                f"ADR-0009: URL sin titulo_fragmento debe quedar en "
                f"{sorted(e.value for e in ESTADOS_SIN_EVIDENCIA)}, no en "
                f"{self.estado_validacion.value!r}. url={self.url}"
            )
        if self.es_oficial is True:
            raise ValueError(
                f"ADR-0009: no se puede afirmar es_oficial=True sin evidencia. url={self.url}"
            )
        return self

    @model_validator(mode="after")
    def _regla_confianza_alta(self) -> "DiscoveryURL":
        """schemas/discovery_schema.md: Alta solo si la URL apunta al municipio
        Y el fragmento evidencia que es la municipalidad.

        Criterio implementado:
          (a) fragmento no vacio, y
          (b) la URL contiene el slug del municipio o 'gob.ar', y
          (c) el fragmento menciona 'municipal*' o el nombre del municipio.

        (c) esta ampliado respecto de la letra del schema ("titulo contiene
        'Municipalidad'") porque el fragmento validado de Navarro en
        data/processed/discovery/discovery_sample_Navarro.json dice
        "...tramites municipales" y quedaria rechazado. Pendiente de confirmacion
        del arquitecto; ver nota en el PR.
        """
        if self.confianza is not Confianza.ALTA:
            return self

        fragmento = normalizar_texto(self.titulo_fragmento or "")
        url_norm = self.url.lower()
        slug = normalizar_slug(self.municipio)
        nombre_norm = normalizar_texto(self.municipio)

        # El schema dice "gob.ar", pero los municipios de PBA usan .gob.ar y
        # .gov.ar indistintamente (munialvear.gov.ar, tresarroyos.gov.ar son
        # oficiales). Ambos son dominios de gobierno argentino.
        dominio_oficial = "gob.ar" in url_norm or "gov.ar" in url_norm
        apunta_al_municipio = (slug and slug in normalizar_slug(url_norm)) or dominio_oficial
        if not apunta_al_municipio:
            raise ValueError(
                f"confianza Alta requiere que la URL contenga el nombre del municipio "
                f"o un dominio oficial (.gob.ar/.gov.ar). "
                f"url={self.url} municipio={self.municipio}"
            )

        evidencia_municipal = "municipal" in fragmento or nombre_norm in fragmento
        if not evidencia_municipal:
            raise ValueError(
                f"confianza Alta requiere que el fragmento mencione 'Municipal*' o "
                f"{self.municipio!r}. fragmento={self.titulo_fragmento!r}"
            )
        return self

    @model_validator(mode="after")
    def _regla_stores_con_id_de_app(self) -> "DiscoveryURL":
        """schemas/discovery_schema.md: si es play_store/app_store debe contener id de app.

        Evita guardar la pagina de resultados de busqueda de la store como si fuera
        la app del municipio.
        """
        url = self.url.lower()
        if self.tipo is TipoURL.PLAY_STORE and not re.search(r"[?&]id=[\w.]+", url):
            raise ValueError(
                f"play_store requiere id de app (?id=paquete.de.la.app). url={self.url}"
            )
        if self.tipo is TipoURL.APP_STORE and not re.search(r"/id\d+", url):
            raise ValueError(f"app_store requiere id de app (/idNNNNNNNN). url={self.url}")
        return self

    # -- serializacion ------------------------------------------------------

    def to_row(self) -> dict:
        """Fila lista para INSERT en discovery_urls (columnas en orden del schema)."""
        return {
            "id": self.id,
            "municipio": self.municipio,
            "id_municipio": self.id_municipio,
            "url": self.url,
            "tipo": self.tipo.value,
            "fuente_query": self.fuente_query,
            "titulo_fragmento": self.titulo_fragmento,
            "fecha_descubrimiento": self.fecha_descubrimiento,
            "confianza": self.confianza.value,
            "estado_validacion": self.estado_validacion.value,
            "es_oficial": self.es_oficial,
        }


# ---------------------------------------------------------------------------
# Resultado por municipio
# ---------------------------------------------------------------------------


class MunicipioDiscovery(BaseModel):
    """Salida de investigar(): el inventario de URLs de un municipio."""

    model_config = ConfigDict(extra="forbid")

    municipio: str = Field(min_length=1)
    id_municipio: str = Field(min_length=1)
    poblacion: Optional[int] = None
    fecha_descubrimiento: str = Field(default_factory=ahora_iso)
    tiempo_ejecucion_segundos: Optional[float] = None
    total_urls: int = 0
    urls: List[DiscoveryURL] = Field(default_factory=list)

    @model_validator(mode="after")
    def _coherencia(self) -> "MunicipioDiscovery":
        # ADR-0010: 20 es techo, no piso.
        if len(self.urls) > MAX_URLS_POR_MUNICIPIO:
            raise ValueError(
                f"ADR-0010: maximo {MAX_URLS_POR_MUNICIPIO} URLs por municipio, "
                f"se recibieron {len(self.urls)} para {self.municipio}"
            )

        # UNIQUE(municipio, url) de la tabla.
        vistas = set()
        for u in self.urls:
            clave = u.url.strip().lower()
            if clave in vistas:
                raise ValueError(
                    f"URL duplicada para {self.municipio}: {u.url} "
                    f"(UNIQUE(municipio, url) en discovery_urls)"
                )
            vistas.add(clave)

            if normalizar_texto(u.municipio) != normalizar_texto(self.municipio):
                raise ValueError(
                    f"URL de otro municipio en el inventario de {self.municipio}: {u.municipio}"
                )

        object.__setattr__(self, "total_urls", len(self.urls))
        return self

    # -- lecturas utiles para los criterios de aceptacion -------------------

    def por_tipo(self, tipo: TipoURL) -> List[DiscoveryURL]:
        return [u for u in self.urls if u.tipo is tipo]

    def por_confianza(self, confianza: Confianza) -> List[DiscoveryURL]:
        return [u for u in self.urls if u.confianza is confianza]

    def con_evidencia(self) -> List[DiscoveryURL]:
        return [u for u in self.urls if u.titulo_fragmento]
