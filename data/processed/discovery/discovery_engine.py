"""
OBSOLETO - No usar. Reemplazado el 2026-08-07 por src/discovery/.

    python src/discovery/discovery_engine.py --municipio Navarro

Este archivo es el scaffold original de Fase 3. Se conserva como referencia
historica del POC de Navarro. Ojo: generaba titulo_fragmento sinteticos del tipo
"Heuristica - URL probable {url}", que violan ADR-0009 (eso no es evidencia, es
la URL mirandose al espejo). El motor nuevo deja esas URLs sin fragmento, con
confianza Baja y estado no_verificable.

---

Fase 3 - Discovery Engine POC
Objetivo: Para 1 municipio, devolver 20 URLs tipificadas en <2 min

Arquitectura:
- Capa 1: Heurística
- Capa 2: Búsqueda (browser.search)
- Capa 3: Validación

Input: municipio nombre (ej: "Navarro")
Output: lista de DiscoveryURL con trazabilidad

Este es scaffold, la implementación real usa browser.search tool en el orquestador
"""

from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime, timezone
import uuid
import re

@dataclass
class DiscoveryURL:
    id: str
    municipio: str
    id_municipio: str
    url: str
    tipo: str
    fuente_query: str
    titulo_fragmento: str
    fecha_descubrimiento: str
    confianza: str
    estado_validacion: str
    es_oficial: bool

# Heurística Capa 1
def generar_urls_heuristicas(municipio: str) -> List[dict]:
    base = municipio.lower().replace(" ", "").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    return [
        {"url": f"https://{base}.gob.ar/", "tipo": "sitio_oficial", "fuente": "heuristica_gob_ar"},
        {"url": f"https://{base}.gob.ar/tramites/", "tipo": "tramites", "fuente": "heuristica_tramites"},
        {"url": f"https://{base}.gob.ar/transparencia/", "tipo": "transparencia", "fuente": "heuristica_transparencia"},
        {"url": f"https://{base}.gob.ar/boletin/", "tipo": "boletin_sibom", "fuente": "heuristica_boletin"},
        {"url": f"https://{base}.gob.ar/salud/", "tipo": "salud_turnos", "fuente": "heuristica_salud"},
    ]

# Ejemplo de output validado para Navarro con evidencia real de Fase 3
def sample_navarro() -> List[DiscoveryURL]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        DiscoveryURL(
            id=f"dis_{uuid.uuid4().hex[:8]}",
            municipio="Navarro",
            id_municipio="MUN-BA-004",
            url="https://navarro.gob.ar/",
            tipo="sitio_oficial",
            fuente_query="Municipalidad de Navarro Buenos Aires sitio oficial",
            titulo_fragmento="Navarro tiene una nueva manera de hacer los trámites municipales, de realizar consultas y de informarse.",
            fecha_descubrimiento=now,
            confianza="Alta",
            estado_validacion="validada",
            es_oficial=True
        ),
        DiscoveryURL(
            id=f"dis_{uuid.uuid4().hex[:8]}",
            municipio="Navarro",
            id_municipio="MUN-BA-004",
            url="https://navarro.gob.ar/tramites-y-servicios/",
            tipo="tramites",
            fuente_query="Municipalidad de Navarro Buenos Aires sitio oficial",
            titulo_fragmento="Tramites y Servicios – Navarro Municipalidad - Registro de proveedores, Habilitación de Comercios",
            fecha_descubrimiento=now,
            confianza="Alta",
            estado_validacion="validada",
            es_oficial=True
        ),
        DiscoveryURL(
            id=f"dis_{uuid.uuid4().hex[:8]}",
            municipio="Navarro",
            id_municipio="MUN-BA-004",
            url="https://navarro.gob.ar/gobierno/",
            tipo="transparencia",
            fuente_query="Municipalidad de Navarro transparencia",
            titulo_fragmento="Gobierno – Navarro Municipalidad",
            fecha_descubrimiento=now,
            confianza="Media",
            estado_validacion="pendiente",
            es_oficial=True
        ),
        DiscoveryURL(
            id=f"dis_{uuid.uuid4().hex[:8]}",
            municipio="Navarro",
            id_municipio="MUN-BA-004",
            url="https://navarro.gob.ar/modernizacion/",
            tipo="gde_expediente",
            fuente_query="Navarro gob ar modernizacion",
            titulo_fragmento="Modernizacion – Navarro Municipalidad",
            fecha_descubrimiento=now,
            confianza="Media",
            estado_validacion="pendiente",
            es_oficial=True
        ),
    ]

def investigar(municipio: str, id_municipio: str) -> List[dict]:
    """
    Función que debe implementar Fase 3 completa.
    Por ahora retorna sample de Navarro.
    Criterio de cierre: <2 min, 8-20 URLs con trazabilidad
    """
    if municipio.lower() == "navarro":
        urls = sample_navarro()
        return [asdict(u) for u in urls]
    else:
        # Para otros municipios, por ahora heurística
        heu = generar_urls_heuristicas(municipio)
        now = datetime.now(timezone.utc).isoformat()
        result = []
        for h in heu:
            result.append({
                "id": f"dis_{uuid.uuid4().hex[:8]}",
                "municipio": municipio,
                "id_municipio": id_municipio,
                "url": h["url"],
                "tipo": h["tipo"],
                "fuente_query": h["fuente"],
                "titulo_fragmento": f"Heurística - URL probable {h['url']}",
                "fecha_descubrimiento": now,
                "confianza": "Baja",
                "estado_validacion": "pendiente",
                "es_oficial": False
            })
        return result

if __name__ == "__main__":
    # POC Navarro
    result = investigar("Navarro", "MUN-BA-004")
    print(f"Navarro - {len(result)} URLs encontradas")
    for r in result:
        print(f" - {r['tipo']}: {r['url']} [{r['confianza']}]")
        print(f"   Evidencia: {r['titulo_fragmento'][:80]}...")