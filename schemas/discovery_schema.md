Schema de Descubrimiento - Fase 3

Version: 1.1 (2026-08-07)
Relacionado: ADR-0009, ADR-0010, ADR-0011, ADR-0012, ADR-0013, diccionario_datos_oficial_v1.md
Implementacion de referencia: src/discovery/schemas.py

    v1.1 sincroniza el contrato con el motor que ya corre. La v1.0 describia un
    estado que el codigo dejo atras: admitia solo https, le faltaban dos estados
    de validacion que los ADRs exigen, y no contemplaba la tabla de municipios.
    Un schema que no coincide con el codigo es peor que no tener schema.

## Tabla: discovery_urls

Cada fila es una URL candidata para un municipio.

| Campo | Tipo | Definicion | Ejemplo |
|---|---|---|---|
| id | String | Hash estable de (municipio, url) | dis_4f1694c3ef74 |
| municipio | String | Nombre exacto del Gold Standard | Navarro |
| id_municipio | String | ID del Gold Standard | MUN-BA-004 |
| url | String | URL absoluta | https://navarro.gob.ar/ |
| tipo | Enum | Tipo tipificado (enum cerrado) | sitio_oficial |
| fuente_query | String | Que la encontro | Municipalidad de Navarro sitio oficial |
| titulo_fragmento | String | Evidencia textual literal | "Navarro Municipalidad" |
| fecha_descubrimiento | Datetime | ISO8601 UTC con sufijo Z | 2026-08-07T12:00:00Z |
| confianza | Enum | Alta / Media / Baja / 0% | Alta |
| estado_validacion | Enum | Ver enum abajo | validada |
| es_oficial | Boolean | Parece oficial. NULL = no se sabe | true |

**id**: hash determinista `sha1(municipio|url)`, no uuid4. Re-correr un
municipio no genera filas nuevas: el PRIMARY KEY queda alineado con la
UNIQUE(municipio, url).

**es_oficial**: NULL es un valor con significado. ADR-0009: desconocido no es
False. Solo pasa a `true` cuando hay evidencia.

## Enum tipo (cerrado)

sitio_oficial, tramites, transparencia, boletin_sibom, salud_turnos,
hacienda_tasas_rafam, reclamos_147, gde_expediente, facebook_oficial,
instagram_oficial, youtube_oficial, play_store, app_store,
normativa_ordenanzas, licitaciones, otro

    docs/Fase3_Plan_Descubrimiento.md usa variantes de estos nombres
    (hacienda_tasas, boletin_oficial, normativa). Manda este schema.

## Enum estado_validacion (cerrado)

| Valor | Significado |
|---|---|
| pendiente | Descubierta, todavia no consultada por HTTP |
| validada | Responde y se leyo su titulo |
| no_verificable | Responde pero sin evidencia legible, o no se pudo determinar |
| no_encontrado | Se consulto y no respondio. ADR-0010 |
| error_404 | Respondio 404 |

    v1.0 solo nombraba validada/pendiente/error_404. Los otros dos los exigen
    ADR-0009 ("estado = No Verificable") y ADR-0010 ("se guarda como No
    Encontrado, no se fabrica").

## Reglas

1. **La URL debe ser absoluta.** Se prefiere `https://` y se admite `http://`
   para los municipios cuyo sitio oficial no ofrece TLS (Rauch, Villarino).
   Nunca se convierte http a https: mataria una URL viva. **ADR-0012.**
2. **Sin fragmento no hay URL valida.** Una URL sin `titulo_fragmento` solo
   puede existir con confianza Baja o 0% y estado `no_verificable` o
   `no_encontrado`, y no puede afirmar `es_oficial = true`. **ADR-0009.**
3. **No se guardan URLs duplicadas por municipio.** La deduplicacion ignora el
   esquema y la barra final: `http://x/a/` y `https://x/a` son la misma pagina.
4. **Confianza Alta** exige: fragmento no vacio, la URL nombra al municipio (o
   variante corta) o es dominio `.gob.ar` / `.gov.ar`, y el fragmento menciona
   `municipal*` o el nombre del municipio. **ADR-0013.**
5. **play_store / app_store** deben contener el id de la app
   (`?id=paquete` o `/idNNNNNNNN`). Si no, se descarta: la pagina de resultados
   de la store no es la app del municipio.
6. **Maximo 20 URLs por municipio.** Es techo, no piso. **ADR-0010.**
7. **Una vez acreditado el sitio oficial**, se descarta lo que viva en otro host,
   salvo registros provinciales y redes/stores. Cierra el paso a los municipios
   homonimos de otras provincias. **ADR-0011.**

Las reglas 1, 2, 4, 5 y 6 estan implementadas como validadores Pydantic que
**levantan excepcion**. No son advertencias: si el motor intenta guardar un dato
que las viola, el proceso falla.

## Tabla: municipios_discovery

Un registro por municipio procesado, **incluidos los que dieron 0 URLs**. Sin
esta tabla un municipio vacio desaparece del archivo y se vuelve indistinguible
de uno no procesado. ADR-0009 exige lo contrario: el vacio se ve.

| Campo | Tipo | Definicion |
|---|---|---|
| id_municipio | TEXT PK | ID del Gold Standard |
| municipio | TEXT UNIQUE | Nombre exacto |
| poblacion | INTEGER | NULL si no consta. Vacio no es 0 |
| fecha_descubrimiento | TEXT | ISO8601 |
| tiempo_ejecucion_segundos | REAL | Cuanto tardo |
| total_urls | INTEGER | Cuantas quedaron |
| urls_con_evidencia | INTEGER | Cuantas tienen fragmento |
| urls_alta | INTEGER | Cuantas con confianza Alta |
| tiene_sitio_oficial | INTEGER | 0 o 1 |
| sitio_sin_https | INTEGER | 1 sin TLS, 0 con TLS, NULL sin sitio. **ADR-0012** |
| estado | TEXT | descubierto / parcial / no_encontrado |

`sitio_sin_https` no es metadato tecnico: un portal sin TLS no puede tener pagos
online seguros ni turnos con datos de salud. Es una senal de madurez digital para
Fase 5.

## DDL

```sql
CREATE TABLE IF NOT EXISTS discovery_urls (
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

CREATE INDEX IF NOT EXISTS idx_municipio ON discovery_urls(municipio);
CREATE INDEX IF NOT EXISTS idx_tipo ON discovery_urls(tipo);

CREATE TABLE IF NOT EXISTS municipios_discovery (
    id_municipio TEXT PRIMARY KEY,
    municipio TEXT NOT NULL UNIQUE,
    poblacion INTEGER,
    fecha_descubrimiento TEXT NOT NULL,
    tiempo_ejecucion_segundos REAL,
    total_urls INTEGER NOT NULL,
    urls_con_evidencia INTEGER NOT NULL,
    urls_alta INTEGER NOT NULL,
    tiene_sitio_oficial INTEGER NOT NULL,
    sitio_sin_https INTEGER,
    estado TEXT NOT NULL
);
```

## Persistencia

El guardado **fusiona por municipio**, no pisa el archivo. Correr 3 municipios
no borra a los otros 83. **ADR-0013.**

## Output JSON

```json
{
  "total_municipios": 86,
  "total_urls": 708,
  "municipios": [
    {
      "municipio": "Navarro",
      "id_municipio": "MUN-BA-004",
      "poblacion": 19000,
      "estado": "descubierto",
      "total_urls": 10,
      "urls": [
        {
          "id": "dis_4f1694c3ef74",
          "url": "https://navarro.gob.ar/",
          "tipo": "sitio_oficial",
          "fuente_query": "heuristica_dominio:navarro.gob.ar",
          "titulo_fragmento": "Navarro Municipalidad",
          "fecha_descubrimiento": "2026-08-07T12:00:00Z",
          "confianza": "Alta",
          "estado_validacion": "validada",
          "es_oficial": true
        }
      ]
    }
  ]
}
```
