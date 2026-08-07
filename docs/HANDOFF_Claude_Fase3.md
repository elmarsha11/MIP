HANDOFF para Claude - Fase 3 Descubrimiento

Para: Claude (Dev)
De: Juli Marshall + Arquitecto MIP (Meta AI)
Fecha: 2026-08-07
Fase: 3 - Descubrimiento
Objetivo: Que investigar("Navarro") devuelva 8-20 URLs tipificadas en <2 min con trazabilidad total
1. Contexto rápido (lee esto primero)

MIP = Municipal Intelligence Platform. Automatiza lo que hoy hace una persona a mano que tardó semanas en llenar un Excel de 86 municipios bonaerenses.

Fase 1 y 2 ya están cerradas:

    Tenemos 86 municipios únicos validados (no 88, 041 y 052 eran duplicados eliminados intencionalmente)
    Gold Standard = data/raw/gold_standard/Estado_de_Municipios_GOLD_86.xlsx - Excel hecho a mano, verificado por persona, lento pero confiable. Es la verdad oficial. Es lo que tenés que automatizar.
    AI Draft = data/raw/ai_draft/UdS_Relevamiento_AI_DRAFT_86.xlsx - Excel hecho con IA, con 7 variables (Portal, GDE, RAFAM, etc) pero sin trazabilidad. Es la wishlist de UDS. Queda en cuarentena, no lo uses para entrenar.
    Población total oficial: 2.101.764 (del Gold Standard)

Tu trabajo en Fase 3 es automatizar el primer paso del investigador: encontrar las URLs oficiales de cada municipio.
2. Qué tenés que leer OBLIGATORIO antes de codear

En orden:

    docs/PROJECT_BLUEPRINT.md - Constitución del proyecto
    decisions/0009-no-ocultar-vacios-con-promedios.md - REGLA DE ORO 1: Si no hay dato, va vacío con confianza 0%, no se promedia, no se inventa
    decisions/0010-fase3-descubrimiento-20-urls.md - REGLA DE ORO 2: Máximo 20 URLs por municipio, sin fragmento no hay URL válida
    schemas/diccionario_datos_oficial_v1.md - Qué cuenta como evidencia para "Tiene App", "Turnos Online", etc
    schemas/discovery_schema.md - Schema exacto de la tabla discovery_urls y enum de tipos
    src/discovery/discovery_engine.py - Scaffold ya funcionando para Navarro
    data/processed/discovery/discovery_sample_Navarro.json - Ejemplo de output válido con citas reales

Si no leíste esos 7 archivos, no codees.
3. Qué tenés que construir

Carpeta: src/discovery/

Archivos a implementar:

src/discovery/
├── discovery_engine.py  (ya existe, es el orquestador, mejoralo)
├── heuristics.py        (NUEVO - Capa 1: genera URLs probables tipo {nombre}.gob.ar)
├── search_provider.py   (NUEVO - Capa 2: hace las 8 queries de búsqueda por municipio)
├── validator.py         (NUEVO - Capa 3: valida que URL responde 200 y contiene nombre municipio)
└── schemas.py           (NUEVO - Pydantic models de DiscoveryURL)

Input: data/processed/gold_standard_86.csv (86 municipios)

Output:

    data/processed/discovery/discovery_urls_86.json - 86 municipios x 8-20 URLs
    data/processed/discovery/discovery_urls_86.sqlite - tabla discovery_urls según schemas/discovery_schema.md

4. Cómo funciona (3 capas)
Capa 1: Heurística (0,5 seg) - heuristics.py
python

def generar_urls_heuristicas(municipio: str) -> List[dict]:
    base = municipio.lower() sin acentos
    return [
        {"url": f"https://{base}.gob.ar/", "tipo": "sitio_oficial"},
        {"url": f"https://{base}.gob.ar/tramites/", "tipo": "tramites"},
        # ... 5 URLs más
    ]

Capa 2: Búsqueda (1,5 min) - search_provider.py

Para cada municipio, ejecutar 8 queries (usá browser.search o requests + Google/Bing scraper):

    "Municipalidad de {nombre} Buenos Aires sitio oficial"
    "Municipalidad de {nombre} transparencia boletin SIBOM"
    "Municipalidad de {nombre} turnos salud online"
    "Municipalidad de {nombre} Facebook oficial"
    "Municipalidad de {nombre} app Play Store"
    "{nombre} gob ar tramites"
    "{nombre} gob ar tasas pagos RAFAM"
    "{nombre} gob ar reclamos 147"

Guardá top 5 resultados por query con título y snippet.
Capa 3: Validación (30 seg) - validator.py
python

def validar(url: str, municipio: str) -> dict:
    # 1. ¿Responde 200?
    # 2. ¿URL contiene nombre municipio o gob.ar?
    # 3. ¿Title contiene "Municipalidad de {nombre}"?
    # Si 2 y 3 = Alta, si solo 2 = Media, si ninguno = Baja

5. Ejemplo validado - Navarro (tu test)

Este es el output que YA funciona y tenés que mantener:
json

{
  "municipio": "Navarro",
  "id_municipio": "MUN-BA-004",
  "total_urls": 4,
  "urls": [
    {
      "url": "https://navarro.gob.ar/",
      "tipo": "sitio_oficial",
      "fuente_query": "Municipalidad de Navarro Buenos Aires sitio oficial",
      "titulo_fragmento": "Navarro tiene una nueva manera de hacer los trámites municipales...",
      "confianza": "Alta",
      "estado_validacion": "validada",
      "es_oficial": true
    },
    {
      "url": "https://navarro.gob.ar/tramites-y-servicios/",
      "tipo": "tramites",
      "fuente_query": "Municipalidad de Navarro Buenos Aires sitio oficial",
      "titulo_fragmento": "Tramites y Servicios – Navarro Municipalidad",
      "confianza": "Alta",
      "estado_validacion": "validada",
      "es_oficial": true
    }
  ]
}

Evidencia real de búsqueda:

    sitio_oficial: "Navarro tiene una nueva manera de hacer los trámites municipales, de realizar consultas y de informarse. – Navarro Municipalidad"
    tramites: "Tramites y Servicios – Navarro Municipalidad"

6. Criterios de aceptación (si no pasa esto, no mergeas)

    python src/discovery/discovery_engine.py --municipio Navarro debe:
        Terminar en <120 segundos
        Devolver 4-20 URLs
        Al menos 1 con tipo sitio_oficial y confianza Alta
        Al menos 1 con tipo tramites o transparencia
        Cada URL con titulo_fragmento no vacío y fuente_query no vacío

    python src/discovery/discovery_engine.py --all debe:
        Procesar los 86 municipios de gold_standard_86.csv
        Generar discovery_urls_86.json y .sqlite
        No duplicar URLs por municipio
        Cumplir schema de schemas/discovery_schema.md

    Validación vs Gold Standard:
        Para Navarro, debe encontrar https://navarro.gob.ar/ (que es el sitio que figura en el Gold Standard manual)

7. Qué NO hacer (te bloqueo PR si haces esto)

    NO inventes URLs. Si no encontrás, guardá como No Encontrado con confianza 0% y estado no_encontrado. ADR-0009.
    NO promedies con municipios vecinos. Si 9 de Julio no tiene turnos online, no le pongas que sí porque Brandsen sí tiene.
    NO uses el AI Draft (data/raw/ai_draft/) como fuente de verdad. Solo como referencia de qué variables quiere UDS medir a futuro.
    NO hardcodees 86 URLs a mano. El motor debe descubrirlas.
    NO guardes URLs sin titulo_fragmento. Sin fragmento no hay dato válido.

8. Primer ticket para arrancar AHORA

Implementá solo esto y hace PR:

Ticket 1: heuristics.py + schemas.py + mejorar discovery_engine.py para que investigar("Navarro") use heurística + devuelva 5 URLs con confianza Baja/Media

Ticket 2: search_provider.py - implementar 8 queries y que Navarro pase de 5 a 10 URLs con confianza Alta

Ticket 3: validator.py + escalar a 86 municipios en paralelo

Arrancá por Ticket 1. Cuando pase tests de Navarro, seguís.
9. Estructura final que tenés que respetar

municipal-intelligence-platform/
├── data/
│   ├── raw/
│   │   ├── gold_standard/Estado_de_Municipios_GOLD_86.xlsx (verdad oficial, no tocar)
│   │   └── ai_draft/UdS_Relevamiento_AI_DRAFT_86.xlsx (wishlist, en cuarentena)
│   └── processed/
│       ├── gold_standard_86.csv
│       ├── gold_standard_86.sqlite
│       └── discovery/
│           ├── discovery_sample_Navarro.json (tu ejemplo válido)
│           ├── discovery_urls_86.json (tu output final)
│           └── discovery_urls_86.sqlite (tu output final)
├── docs/
├── schemas/
├── decisions/
└── src/discovery/

¿Listo? Empezá por leer los 7 archivos obligatorios y después Ticket 1.

Cualquier duda, preguntale al arquitecto (Meta AI) por qué se tomó cada decisión en Fase 2.