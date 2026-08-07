Schema de Descubrimiento - Fase 3

Versión: 1.0
Relacionado: ADR-0009, diccionario_datos_oficial_v1.md
Tabla: discovery_urls

Cada fila es una URL candidata para un municipio.
Campo	Tipo	Definición	Ejemplo
id	String	UUID	dis_001
municipio	String	Nombre exacto Gold Standard	Navarro
id_municipio	String	ID Gold Standard	MUN-BA-004
url	String	URL candidata	https://navarro.gob.ar/
tipo	Enum	Tipo tipificado	sitio_oficial
fuente_query	String	Query que la encontró	Municipalidad de Navarro sitio oficial
titulo_fragmento	String	Título o snippet que evidencia	"Navarro tiene una nueva manera..."
fecha_descubrimiento	Datetime	ISO8601	2026-08-07T12:00:00Z
confianza	Enum	Alta / Media / Baja	Alta
estado_validacion	Enum	validada / pendiente / error_404	pendiente
es_oficial	Boolean	¿Parece oficial?	true
Enum tipo (cerrado)

    sitio_oficial
    tramites
    transparencia
    boletin_sibom
    salud_turnos
    hacienda_tasas_rafam
    reclamos_147
    gde_expediente
    facebook_oficial
    instagram_oficial
    youtube_oficial
    play_store
    app_store
    normativa_ordenanzas
    licitaciones
    otro

Reglas

    URL debe ser absoluta con https://
    No se guardan URLs duplicadas por municipio+tipo+url (unique constraint)
    confianza Alta solo si url contiene nombre municipio o gob.ar + titulo contiene "Municipalidad"
    Si es play_store/app_store, debe contener id de app
    ADR-0009: si no hay fragmento, confianza = Baja y estado = No Verificable

Output JSON ejemplo
json

{
  "municipio": "Navarro",
  "id_municipio": "MUN-BA-004",
  "total_urls": 8,
  "urls": [
    {
      "url": "https://navarro.gob.ar/",
      "tipo": "sitio_oficial",
      "fuente_query": "Municipalidad de Navarro Buenos Aires sitio oficial",
      "titulo_fragmento": "Navarro tiene una nueva manera de hacer los trámites municipales...",
      "confianza": "Alta",
      "fecha_descubrimiento": "2026-08-07T12:00:00Z"
    }
  ]
}

Tabla SQLite
sql

CREATE TABLE discovery_urls (
    id TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    url TEXT NOT NULL,
    tipo TEXT NOT NULL,
    fuente_query TEXT,
    titulo_fragmento TEXT,
    fecha_descubrimiento TEXT NOT NULL,
    confianza TEXT NOT NULL CHECK(confianza IN ('Alta','Media','Baja','0%')),
    estado_validacion TEXT NOT NULL,
    es_oficial BOOLEAN,
    UNIQUE(municipio, url)
);

CREATE INDEX idx_municipio ON discovery_urls(municipio);
CREATE INDEX idx_tipo ON discovery_urls(tipo);