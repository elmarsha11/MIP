"""
Capa 1 - Heuristica (~0,5 s por municipio).

Genera URLs PROBABLES a partir del nombre del municipio. No consulta la red y no
verifica nada, por lo tanto ninguna URL de esta capa tiene evidencia.

ADR-0009 aplicado literalmente: una URL heuristica sale con
    titulo_fragmento  = None      (no hay fragmento: no inventamos uno)
    confianza         = Baja
    estado_validacion = no_verificable
    es_oficial        = None      (desconocido, que no es False)

La Capa 2 (search_provider) le adosa evidencia real y la Capa 3 (validator) la
promueve a Media/Alta o la baja a no_encontrado/error_404.
"""

from __future__ import annotations

from typing import List, Optional

try:  # ejecutado como paquete (import src.discovery.heuristics)
    from .schemas import (
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        ahora_iso,
        normalizar_slug,
        quitar_acentos,
    )
except ImportError:  # ejecutado como script (python src/discovery/discovery_engine.py)
    from schemas import (  # type: ignore[no-redef]
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        ahora_iso,
        normalizar_slug,
        quitar_acentos,
    )

# Dominio institucional estandar de municipios de PBA.
DOMINIO_BASE = "gob.ar"

# Patrones alternativos de dominio observados en PBA. Off por defecto: multiplican
# candidatas sin evidencia. Los activa Ticket 3 cuando el validador pueda descartarlas
# con una llamada HTTP barata.
PLANTILLAS_DOMINIO_ALTERNATIVAS = (
    "muni{slug}.gob.ar",
    "{slug}.mun.gob.ar",
)

# (path, tipo, id_patron). El id_patron va a fuente_query para trazabilidad:
# permite saber por que se propuso cada URL.
PATRONES_PATH = (
    ("", TipoURL.SITIO_OFICIAL, "heuristica_gob_ar"),
    ("tramites/", TipoURL.TRAMITES, "heuristica_tramites"),
    ("transparencia/", TipoURL.TRANSPARENCIA, "heuristica_transparencia"),
    ("boletin/", TipoURL.BOLETIN_SIBOM, "heuristica_boletin"),
    ("salud/", TipoURL.SALUD_TURNOS, "heuristica_salud"),
)

PREFIJO_FUENTE = "heuristica:"


def dominio_municipio(municipio: str) -> str:
    """'Coronel Suárez' -> 'coronelsuarez.gob.ar'."""
    return f"{normalizar_slug(municipio)}.{DOMINIO_BASE}"


def generar_urls_heuristicas(
    municipio: str,
    id_municipio: str,
    fecha: Optional[str] = None,
    incluir_dominios_alternativos: bool = False,
) -> List[DiscoveryURL]:
    """Devuelve las URLs candidatas de Capa 1 para un municipio.

    Por defecto son 5 (una por patron de path sobre {slug}.gob.ar). Todas salen
    con confianza Baja y sin fragmento: son hipotesis, no hallazgos.
    """
    slug = normalizar_slug(municipio)
    if not slug:
        raise ValueError(f"No se pudo derivar slug del municipio {municipio!r}")

    fecha = fecha or ahora_iso()
    dominios = [(f"{slug}.{DOMINIO_BASE}", "")]
    if incluir_dominios_alternativos:
        dominios += [
            (plantilla.format(slug=slug), f"|{plantilla.format(slug='X')}")
            for plantilla in PLANTILLAS_DOMINIO_ALTERNATIVAS
        ]

    urls: List[DiscoveryURL] = []
    vistas = set()
    for dominio, sufijo_patron in dominios:
        for path, tipo, id_patron in PATRONES_PATH:
            url = f"https://{dominio}/{path}"
            if url in vistas:
                continue
            vistas.add(url)
            urls.append(
                DiscoveryURL(
                    municipio=municipio,
                    id_municipio=id_municipio,
                    url=url,
                    tipo=tipo,
                    fuente_query=f"{PREFIJO_FUENTE}{id_patron}{sufijo_patron}",
                    titulo_fragmento=None,  # ADR-0009: sin evidencia, no se inventa
                    fecha_descubrimiento=fecha,
                    confianza=Confianza.BAJA,
                    estado_validacion=EstadoValidacion.NO_VERIFICABLE,
                    es_oficial=None,
                )
            )
    return urls


def es_url_heuristica(url: DiscoveryURL) -> bool:
    """True si la URL viene de Capa 1 (util para reportes y para Ticket 3)."""
    return url.fuente_query.startswith(PREFIJO_FUENTE)


__all__ = [
    "DOMINIO_BASE",
    "PATRONES_PATH",
    "PLANTILLAS_DOMINIO_ALTERNATIVAS",
    "PREFIJO_FUENTE",
    "dominio_municipio",
    "es_url_heuristica",
    "generar_urls_heuristicas",
    "normalizar_slug",
    "quitar_acentos",
]
