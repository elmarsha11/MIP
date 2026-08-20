# Seguridad — cuánto delito se denuncia en cada municipio

> Fase 3 encontró **dónde** mirar. Fase 4 reportó **qué dicen** los portales.
> `src/gabinete` responde **quién** está a cargo.
> Esto responde **cuánto delito se denuncia**, con la fuente oficial.

Es el **primero de los dos ejes** de seguridad. El segundo —cómo operan, qué
operativos hacen, qué fuerzas actúan— no está en ninguna estadística y sale de
los medios locales. Este módulo es la línea base contra la cual se leerá aquello.

## Fuente

**SNIC** — Sistema Nacional de Información Criminal, Dirección Nacional de
Estadística Criminal del Ministerio de Seguridad de la Nación.

| | |
|---|---|
| Serie | 2000 a 2025, anual |
| Desagregación | por departamento (= partido) |
| Tipos de delito | 69 |
| Normalización | `tasa_hechos` por 100.000 habitantes, ya calculada |
| Cobertura del relevamiento | **86 de 86** |

```bash
python src/seguridad/motor_seguridad.py --todos          # calcular y guardar
python src/seguridad/motor_seguridad.py --ficha Chascomus
python src/seguridad/motor_seguridad.py --ranking
```

## La decisión que define el número

El SNIC no trae una fila "total": hay que sumar. **Sumar los 69 tipos parece lo
neutral y es lo que arruina el número.**

El delito más frecuente de Chascomús en 2025 es *"Tenencia simple atenuada para
uso personal de estupefacientes"*, con **693 hechos**. Eso no mide cuánto delito
sufre un vecino: mide **cuánta gente palpa la policía**. Sumándolo, un partido
con despliegue activo en drogas aparece como más inseguro que uno donde la
policía no sale — exactamente al revés.

Por eso el índice se arma con delitos **donde hay una víctima que denuncia un
daño**:

| Grupo | Ejemplos |
|---|---|
| Contra las personas | homicidios, lesiones dolosas, amenazas |
| Contra la propiedad | robos, hurtos, tentativas, daños |
| Integridad sexual | abusos, violaciones |

**Fuera del índice, informado aparte:** estupefacientes y armas. No son "menos
importantes" — miden otra cosa: despliegue de la fuerza, que es justamente el
segundo eje.

**Fuera de todo:** *Suicidios (consumados)*. El SNIC lo publica porque su
registro pasa por la policía, no porque sea un delito contra un tercero.
Contarlo como "inseguridad" sería un error de categoría.

## Las cuatro advertencias que viajan con el número

**1. Son denuncias, no delitos.** Donde se denuncia menos, el número baja sin que
baje el delito. Es la limitación conocida del SNIC y no se puede corregir desde
acá.

**2. El nivel es relativo a los 86.** *"Alto"* significa *"en el tercio superior
de los municipios relevados"*, **no** *"peligroso"*. Se calcula por terciles
sobre el conjunto, así que la misma tasa puede ser alta en un conjunto y baja en
otro.

**3. El índice deja afuera lo que detecta la policía**, no lo que sufre la gente.

**4. Los partidos balnearios tienen la tasa inflada.** La tasa divide por
población **residente**, pero en verano esos partidos reciben mucha más gente.
Medido sobre 2025: **6 de los 10 primeros son balnearios**, y 10 de los 29
"alto", siendo apenas 14 de los 86.

No se corrige — corregirlo exigiría población turística por partido, que no
existe, y estimarla sería inventar (ADR-0009). **Se marca con `*` y se avisa.**

## Trampas encontradas armando esto

- **El SNIC se renombra a sí mismo.** Coronel Rosales figura como *"Coronel de
  Marina L. Rosales"* hasta 2016 y *"Coronel de Marina Leonardo Rosales"* desde
  2017. Con un solo alias el partido perdía nueve años.
- **Un hueco solitario arrastraba a los 86 al pasado.** La primera versión pedía
  el año común a *todos* y devolvía **2016** porque un único partido tenía un
  bache. Ahora se toma el año más nuevo con 90% de cobertura y se declara quién
  falta.
- **El formato de números.** El atajo `.replace(",", ".")` sobre un formato
  inglés convierte el separador de miles pero deja el decimal en punto: `2.324,8`
  salía impreso como `2.324.8`.

## Archivos

| Archivo | Qué tiene |
|---|---|
| `indice.py` | Qué delitos entran, cuáles no, y por qué. La decisión metodológica |
| `snic.py` | Descarga, parseo, alias y elección del año de referencia |
| `motor_seguridad.py` | Orquestador, CLI, ficha y ranking |

El CSV son 67 MB: se cachea en `data/processed/seguridad/cache/` pero **no se
versiona**, a diferencia de los cuadros de INDEC. Se rebaja con `--refrescar`.

## En el tablero

Pestaña **Seguridad**, con los dos ejes uno al lado del otro: cuánto (SNIC) y
cómo opera (prensa), cada uno con su propia distribución. Se filtra por nivel y
por aspecto a la vez — son preguntas independientes, no una lista de categorías
donde se elige una.

**Excel** (`src/exportar/libro_excel.py:exportar_seguridad`): dos hojas, una por
eje, igual que en el libro completo. Mismo motivo que en ambiental: mezclar un
número del SNIC con una cita de diario en la misma tabla haría parecer que
pesan lo mismo.

**PDF** (`src/exportar/informe_seguridad_pdf.py`): el informe que la ficha por
municipio no da — los 86 juntos, para decidir a quién visitar en vez de leer
sobre uno ya elegido. Apaisado, con la portada llevando las cuatro advertencias
del índice más la de cómo-opera, porque el informe se imprime y se lee suelto,
sin la ficha al lado que las explique.

```bash
python src/exportar/informe_seguridad_pdf.py
```

En el HTML exportado sin servidor no hay quien genere ninguno de los dos: el
Excel se reemplaza por un CSV armado en el navegador con los mismos datos, y el
botón del PDF se deshabilita explicándose (`requiere servidor`) en vez de
desaparecer — esconderlo fue el error que costó una vuelta completa con el
Excel de ambiental.
