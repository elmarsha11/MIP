Fase 3 - Resultados del Descubrimiento

Fecha de corrida: 2026-08-07
Codigo: src/discovery/
Contratos: ADR-0009, ADR-0010, ADR-0011, ADR-0012, schemas/discovery_schema.md
Salidas: data/processed/discovery/discovery_urls_86.json y .sqlite

## Resumen

| Metrica | Valor |
|---|---|
| Municipios procesados | 86 / 86 |
| Tiempo de una corrida completa | ~170 segundos |
| Tiempo por municipio | ~8 s (criterio de cierre: <120 s) |
| URLs descubiertas | 708 |
| Promedio por municipio | 8,2 (ADR-0010: 20 es maximo, no minimo) |
| **Municipios con sitio oficial identificado** | **85 / 86** |
| Municipios sin ninguna URL | 0 |
| URLs sin fragmento de evidencia | 0 |
| URLs sin query de origen | 0 |
| Tipos distintos cubiertos por municipio | 5,5 promedio |
| Tests | 86, en verde |

El trabajo manual que llevaba 43 horas (30 min x 86 municipios) corre en menos de 3 minutos.

## Cobertura por tipo

| Tipo | Municipios |
|---|---|
| boletin_sibom | 86 |
| sitio_oficial | 85 |
| salud_turnos | 56 |
| tramites | 50 |
| transparencia | 44 |
| licitaciones | 32 |
| hacienda_tasas_rafam | 26 |
| gde_expediente | 21 |
| normativa_ordenanzas | 14 |
| reclamos_147 | 11 |

Confianza: 386 Alta, 312 Media, 4 Baja. Cero URLs sin evidencia.

## Validacion contra el Gold Standard

Navarro (POC de ADR-0010): el motor encuentra `https://navarro.gob.ar/` con
confianza Alta, que es exactamente el sitio que la persona cargo a mano en el
Gold Standard. Tambien encuentra `/tramites-y-servicios/`, la URL citada como
evidencia en ADR-0010.

## El municipio que falta

**Exaltacion de la Cruz.** Tanto el SIBOM como Wikidata publican
`exaltaciondelacruz.gov.ar`, que hoy no responde ni en http ni en https. Ningun
patron de dominio da resultado.

Por ADR-0009 queda como **No Encontrado**, no como 0 ni como promedio de sus
vecinos. Igual tiene su boletin en SIBOM. Es una tarea de investigacion, no un
dato faltante que se tapa.

Para reintentarlo cuando el portal vuelva:

```bash
python src/discovery/discovery_engine.py --faltantes
```

## Hallazgos que valen como producto, no solo como pipeline

**Dos municipios no tienen HTTPS.** Rauch y Villarino sirven su sitio oficial
solo por `http://`. Un portal sin TLS no puede tener pagos online seguros ni
turnos con datos de salud: es una senal directa de nivel Basico. Queda
registrado en la columna `sitio_sin_https` de `municipios_discovery`. Ver ADR-0012.

**Municipios homonimos de otras provincias.** `veinticincodemayo.gob.ar` es de
San Juan, `rivadavia.gob.ar` es de San Juan, `maipu.gob.ar` es de Mendoza. Los
tres pasan cualquier chequeo de titulo. El guardia de provincia los descarta y
el motor busca el bonaerense: Maipu de Buenos Aires es `maipu-gba.gob.ar`.

**Dominios que no se parecen al nombre.** Villa Gesell es `gesell.gob.ar`,
Monte Hermoso es `montehermoso.gov.ar`, Tordillo es `tordillomunicipio.org`,
San Antonio de Areco es `areco.ar`, Rauch es `rauch.mun.gba.gov.ar`. Ningun
patron los encuentra: salen de los registros (SIBOM y Wikidata).

## Errores que el pipeline evita

**Notas de prensa disfrazadas de seccion.** Los portales WordPress redirigen
`/salud/` a la nota mas parecida. `navarro.gob.ar/salud-para-todos-mas-de-380-
vecinas-y-vecinos-atendidos-en-el-caps/` llegaba tipificada como `salud_turnos`
con confianza Alta. Ahora se re-tipifica despues del redirect.

**URLs de otro host colandose como el sitio del municipio.** Una vez acreditado
el dominio oficial, se descarta lo que viva en otro host. Era el agujero por el
que entraba el homonimo de otra provincia.

**Dominios oficiales que no son del municipio.** arba.gov.ar y el SIBOM
provincial son .gob.ar y no son de ningun municipio en particular.

**Perder un municipio porque su servidor tardo.** Las URLs de registros se
reintentan hasta 3 veces, las pistas se consultan en serie antes de paralelizar,
y el guardado fusiona por municipio en vez de pisar el archivo.

## Como correrlo

```bash
python src/discovery/discovery_engine.py --municipio Navarro
python src/discovery/discovery_engine.py --all
python src/discovery/discovery_engine.py --faltantes
python src/discovery/discovery_engine.py --listar-municipios
python -m unittest discover -s tests -v
```

Banderas: `--solo-heuristica` (sin red), `--sin-sitio`, `--sin-registros`,
`--sin-busqueda`, `--sin-validar`, `--offline`, `--limite N`, `--workers N`,
`--json`, `--sqlite`.

## Estado de los criterios de aceptacion del HANDOFF

| Criterio | Estado |
|---|---|
| `--municipio Navarro` termina en <120 s | Si (~9 s) |
| Devuelve 4-20 URLs | Si (10) |
| Al menos 1 sitio_oficial con confianza Alta | Si |
| Al menos 1 de tramites o transparencia | Si |
| Cada URL con titulo_fragmento y fuente_query no vacios | Si (0 vacios en 708) |
| `--all` procesa los 86 y genera JSON + SQLite | Si |
| No duplica URLs por municipio | Si (UNIQUE en el modelo y en la tabla) |
| Cumple schemas/discovery_schema.md | Si, con la salvedad de ADR-0012 (http) |

## Pendiente para Fase 4

- Exaltacion de la Cruz.
- La cosecha lee solo la home; falta un segundo nivel de navegacion. Subiria la
  cobertura de tramites (50/86) y transparencia (44/86).
- `facebook_oficial`, `instagram_oficial` y `play_store` casi no aparecen: son
  las que mas dependen de la Capa 2 de busqueda, hoy limitada por el buscador.
- El diccionario pide diferenciar turnos online reales de una pagina de salud
  informativa. Eso es Fase 4 (scraping con 5 sellos), no descubrimiento.
