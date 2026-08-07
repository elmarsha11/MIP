# src/discovery - Fase 3: Descubrimiento

Encuentra las URLs oficiales de cada uno de los 86 municipios del Gold Standard,
tipificadas y con trazabilidad completa.

```bash
python src/discovery/discovery_engine.py --municipio Navarro
python src/discovery/discovery_engine.py --all
python src/discovery/discovery_engine.py --faltantes   # reintenta los sin sitio
python -m unittest discover -s tests -v
```

Estado: 86/86 municipios procesados, 85 con sitio oficial, 708 URLs, 0 sin
evidencia. Ver `docs/Fase3_Resultados.md`.

## Modulos

| Archivo | Capa | Que hace |
|---|---|---|
| `schemas.py` | - | Modelos Pydantic. ADR-0009 y ADR-0010 son validadores que **levantan excepcion**, no advertencias |
| `heuristics.py` | 1 | URLs probables a partir del nombre. Sin red, sin evidencia |
| `site_crawler.py` | 2 | Dominio oficial por HTTP + cosecha de enlaces de la home. Fuente primaria |
| `registries.py` | 2 | SIBOM, ficha provincial de gba.gob.ar y Wikidata (P856) |
| `search_provider.py` | 2 | Las 8 queries del HANDOFF. Complementaria y degradable |
| `validator.py` | 3 | HTTP 200 + `<title>`. Define la confianza final |
| `storage.py` | - | JSON + SQLite segun `schemas/discovery_schema.md` |
| `discovery_engine.py` | - | Orquestador y CLI |

## Las reglas que el codigo hace cumplir

**Sin fragmento no hay URL valida** (ADR-0009). Una URL sin evidencia textual
solo puede existir como candidata con confianza Baja y estado `no_verificable`.
Si el codigo intenta guardarla como Alta, el modelo levanta `ValidationError` y
el pipeline se corta. Es intencional: preferimos romper antes que publicar un
dato inventado.

**20 es maximo, no minimo** (ADR-0010). Si un municipio tiene 4 URLs reales, se
guardan 4. `MunicipioDiscovery` rechaza mas de 20.

**Desconocido no es False.** `es_oficial=None` significa "todavia no se sabe".
Solo pasa a `True` cuando hay evidencia.

**El vacio se ve.** Un municipio sin URLs igual queda registrado en la tabla
`municipios_discovery` con estado `no_encontrado`. Si desapareciera del archivo
seria indistinguible de uno no procesado.

## Confianza

| Nivel | Condicion |
|---|---|
| Alta | Responde 200 + la URL apunta al municipio + el `<title>` lo acredita |
| Media | Responde 200 + la URL apunta al municipio, pero el titulo no lo acredita |
| Baja | Ninguna de las dos, o la URL dejo de responder |
| 0% | No investigado (ADR-0009) |

## Cosas no obvias

- **`id_municipio` no esta en el Gold Standard.** Se cruza con
  `Matriz-86-municipios.csv` por slug normalizado. Es el unico uso permitido de
  ese archivo en cuarentena: identidad, no variables. Ver `ALIAS_ID_MUNICIPIO`.
- **Hay municipios homonimos en otras provincias.** Maipu, Rivadavia, 25 de Mayo,
  Castelli, Colon, General Alvear existen tambien en Mendoza, San Juan, Entre
  Rios. `provincia_ajena()` los filtra. Ver ADR-0011.
- **Los portales WordPress redirigen `/salud/` a la nota mas parecida.** Por eso
  el tipo se recalcula despues de cada redirect.
- **El buscador cachea en disco** (`data/processed/discovery/cache/`). Sirve para
  no re-consultar, para correr con `--offline` y para auditar de donde salio
  cada fragmento.
- **Dos municipios no tienen HTTPS** (Rauch, Villarino). El motor admite `http://`
  y lo registra en `municipios_discovery.sitio_sin_https`: no tener TLS es un
  dato de madurez digital, no un error. Ver ADR-0012.
- **Nunca se fuerza `http` a `https`.** Convertirla mataria una URL viva: se
  prueban los dos esquemas, https primero.
- **Los IDs son deterministicos** (`sha1(municipio|url)`), no uuid4: re-correr un
  municipio no genera filas nuevas.

## Deuda conocida

- La cosecha lee solo la home, no un segundo nivel de navegacion.
- 1 municipio sin sitio oficial (Exaltacion de la Cruz, portal caido).
- `search_provider` depende de que la IP no este limitada por DuckDuckGo.
