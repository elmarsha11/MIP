Fase 3 - Plan de Descubrimiento (20 URLs)

Versión: 1.0 - En curso
Fecha inicio: 2026-08-07
Fase anterior: Fase 2 CERRADA (86 municipios únicos, Gold Standard definido)
Criterio de cierre Fase 3: investigar("Navarro") devuelve 20 URLs tipificadas en <2 min sin intervención humana.
Objetivo Fase 3

Automatizar el primer paso que hace la persona que verificó tu Excel a mano:

    Abrir Google, buscar "Municipalidad de Navarro oficial", "Navarro transparencia", "Navarro turnos salud", "Municipalidad Navarro Facebook", "Mi Navarro app Play Store"

Hoy eso tarda 30 minutos por municipio x 86 = 43 horas. MIP debe hacerlo en <2 min por municipio x 86 = 2,8 horas total.
Entregable

Para cada uno de los 86 municipios, un inventario de 15-25 URLs candidatas tipificadas con:

    url
    tipo (enum cerrado)
    fuente de descubrimiento (google, bing, heurística)
    confianza inicial
    fecha descubrimiento

Tabla SQLite: data/processed/discovery/discovery_urls.sqlite
Tipos de URL a descubrir (enum cerrado)

    sitio_oficial - Ej: https://navarro.gob.ar/ 1
    tramites - /tramites, /guia-tramites, /servicios
    transparencia - /transparencia, /gobierno-abierto, /boletin, /SIBOM
    salud_turnos - /salud, /turnos, /caps, /hospital
    hacienda_tasas - /rentas, /tasas, /rafam, /pagos, /arba, /autogestion
    reclamos_147 - /147, /atencion-ciudadana, /reclamos
    gde_expediente - /gde, /expediente, /mesa-entradas
    facebook_oficial - facebook.com/MunicipalidadDe...
    instagram_oficial
    play_store - app municipal Android
    app_store - app municipal iOS
    boletin_oficial - /boletin, SIBOM
    normativa - /ordenanzas, /normativa
    licitaciones

Estrategia de Descubrimiento (3 capas)
Capa 1: Heurística (0,5 seg)

Construir URLs probables a partir del nombre:

    {nombre}.gob.ar
    {nombre}.mga.gov.ar (algunos usan)
    muni{nombre}.gob.ar

Ej: navarro.gob.ar existe y es oficial 1, Tramites y Servicios está en /tramites-y-servicios 2
Capa 2: Búsqueda web (1,5 min)

Para cada municipio, 8 queries:

    "Municipalidad de {nombre} Buenos Aires sitio oficial"
    "Municipalidad de {nombre} transparencia boletin SIBOM"
    "Municipalidad de {nombre} turnos salud online"
    "Municipalidad de {nombre} Facebook oficial"
    "Municipalidad de {nombre} app Play Store"
    "{nombre} gob ar tramites"
    "{nombre} gob ar tasas pagos RAFAM"
    "{nombre} gob ar reclamos 147"

Usamos browser.search, guardamos top 5 resultados por query.
Capa 3: Validación (30 seg)

    ¿La URL contiene {nombre} o "municipalidad" o "gob.ar"?
    ¿Responde 200?
    ¿Tiene en title "Municipalidad de {nombre}"?
    Si sí, confianza Alta. Si no, Media/Baja.

Ejemplo Real: Navarro (validación de Fase 3)

Con la búsqueda que acabamos de hacer:

    sitio_oficial: https://navarro.gob.ar/ - confianza Alta - fuente: search query 1 - evidencia: "Navarro tiene una nueva manera de hacer los trámites..." 1
    tramites: https://navarro.gob.ar/tramites-y-servicios/ - confianza Alta - fuente: search result - evidencia: "Tramites y Servicios – Navarro Municipalidad" 2
    gobierno: https://navarro.gob.ar/gobierno/ - para transparencia
    modernizacion: https://navarro.gob.ar/modernizacion/ - para GDE/app
    facebook: buscar "Navarro Municipalidad Facebook" (pendiente)
    play_store: buscar "Mi Navarro app" (en Gold Standard figura "App Mi Navarro / En desarrollo")

Esto es exactamente lo que hacía a mano la persona que te armó el Excel Gold Standard.
Arquitectura Técnica

src/discovery/
├── discovery_engine.py  # orquesta las 3 capas
├── heuristics.py        # capa 1
├── search_provider.py   # capa 2 - wrapper de browser.search
├── validator.py         # capa 3
└── schemas.py           # pydantic models

Input: data/processed/gold_standard_86.csv
Output: data/processed/discovery/discovery_urls.sqlite + discovery_urls_86.json
Criterios de Calidad Fase 3 (ADR-0009)

    No se inventa URL. Si no se encuentra, se guarda como No Encontrado, no se fabrica.
    Cada URL con: url, tipo, municipio, fecha, fuente_query, fragmento_titulo, confianza.
    Sin fragmento no hay URL válida.
    20 URLs por municipio no es obligatorio, es máximo. Si solo hay 8 reales, se guardan 8.

Próximos pasos

    Implementar discovery_engine.py con 1 municipio (Navarro) como POC
    Validar contra Gold Standard: ¿las URLs que encuentra MIP son las que usó la persona a mano?
    Escalar a 86 municipios en paralelo (subagents)
    Congelar Fase 3

¿Avanzamos con el POC de Navarro?

    Navarro tiene una nueva manera de hacer los trámites municipales, de realizar consultas y de informarse. – Navarro Municipalidad — https://navarro.gob.ar/navarro-tiene-una-nueva-manera-de-hacer-los-tramites-municipales-de-realizar-consultas-y-de-informarse/ ↩ ↩
    2
    ↩
    3

    Tramites y Servicios – Navarro Municipalidad — https://navarro.gob.ar/tramites-y-servicios/ ↩ ↩
    2

