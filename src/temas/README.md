# Motor de temas — rastrear una pregunta nueva sobre los 86

> Fase 3 encontró **dónde** mirar. Fase 4 reportó **qué dicen** los portales sobre
> once variables de gobierno digital. Esto responde **una pregunta que Fase 4
> nunca hizo**, sin tocar su evidencia.

## Por qué existe

Fase 4 pregunta once variables y las once son de gobierno digital: app, boletín,
turnos, pagos, expedientes, licitaciones, RAFAM, reclamos 147, trámites,
transparencia. Cuando aparece un tema nuevo —ambiental, producción, obra— no hay
por dónde entrar sin escribir otro motor entero.

Peor: **las fuentes tampoco están**. Al 2026-08-15, de las 708 URLs que descubrió
Fase 3, seis rozaban lo ambiental y la mitad eran tasas de higiene, que son un
impuesto y no una política. El único hallazgo ambiental en la base era
`Centro Ambiental de Chascomús`, de un solo municipio.

| | |
|---|---:|
| Hallazgos de Fase 4 con señal ambiental | 2 de 955 |
| URLs descubiertas con señal ambiental | 6 de 708 |
| Tipos de URL de Fase 3 que sean ambientales | 0 de 11 |

Por eso este motor no relee: **cosecha**. Y por eso un tema es configuración y no
código, para que el siguiente no cueste otro motor.

## Qué hace

```bash
python src/temas/motor_temas.py --listar-temas
python src/temas/motor_temas.py --tema ambiental --municipio Navarro
python src/temas/motor_temas.py --tema ambiental --all
python src/temas/motor_temas.py --tema ambiental --all --con-prensa
python src/temas/motor_temas.py --tema ambiental --ficha Navarro
python src/temas/motor_temas.py --tema ambiental --cobertura
```

Las dos últimas no llaman a la IA: leen lo ya rastreado.

## Un tema es configuración

Agregar un tema es agregar un `Tema` a `definiciones.py`. Nada más. El motor, la
cosecha, el prompt y la verificación son los mismos para todos.

```python
SubTema(
    id="promotores_ambientales",
    pregunta="El municipio tiene un programa de promotores ambientales?",
    que_prueba="La cita tiene que nombrar el programa como algo que el municipio tiene.",
    senales=("promotor ambiental", "educacion ambiental", ...),
    queries=('"{municipio}" municipio "promotores ambientales"', ...),
    organismos_ajenos=(),      # quién NO es el municipio
    exige_hecho=True,          # un anuncio a futuro no confirma
)
```

Las **señales** eligen qué leer, no qué responder. Que una página diga "ambiente"
la hace candidata; lo que diga lo sigue decidiendo el modelo con cita verificada.
Van sin tildes: se cotejan contra texto normalizado.

## La cosecha, en tres patas

De más barata a más cara:

1. **Lo ya descubierto** que sirve al tema: portal, trámites, ordenanzas y
   boletín. `urls_de_municipio` de Fase 4 no alcanza, porque deduplica a una
   página por tipo y deja SIBOM afuera. Acá entra además cualquier URL —del tipo
   que sea— cuyo título o dirección mencione una señal: es lo que rescata el
   digesto ambiental de Laprida, que Fase 3 archivó como `otro`.
2. **El portal recorrido con las señales del tema.** Es la cosecha dirigida que
   Fase 4 usa para turnos, generalizada. Ahí vive la página de residuos que nadie
   clasificó.
3. **Los boletines oficiales**, leídos con `src/gabinete/sibom.py`. No se baja la
   URL de SIBOM que descubrió Fase 3: esa es `cities/N`, la página de **listado**
   del municipio, y su HTML es un índice sin contenido. El lector de gabinete
   navega de ahí a los boletines y les saca el texto con `pypdf`.
4. **Prensa local**, si se pide con `--con-prensa`.

### Alcance de los boletines

65 de los 86 municipios publican en SIBOM; los otros 21 están registrados pero
nunca publicaron. Y se leen **sin paginar**: los más recientes. Eso alcanza para
lo que el municipio decidió últimamente, no para un programa creado por ordenanza
en 2019 — eso vive en el digesto, que pocos publican.

La primera corrida es lenta porque baja PDFs. Quedan cacheados en
`data/processed/gabinete/cache`, compartidos con el motor de gabinete: si ese ya
corrió, esta parte es instantánea. Con `--sin-boletines` se saltea.

### Documentos largos: ventanas, no recorte

Un boletín de SIBOM son 320.000 caracteres y en el prompt entran 4.000. Cortar
por el principio deja la carátula y el índice, con la ordenanza ambiental en la
página 60. Por eso `fragmentos_relevantes` extrae ventanas alrededor de cada
señal y las pega con un separador. Si no hay ninguna señal, cae al principio: la
página puede ser corta y hablar del tema con otras palabras.

Una cita que cruce dos ventanas no verifica, y está bien: es el lado seguro del
error.

## La regla que lo sostiene

**La IA propone, el código verifica** (ADR-0014), en dos pasos:

1. **La cita existe literal** en alguna de las páginas que se le mostraron. Se
   prueba contra todas y no solo contra la que dijo el modelo: el índice de
   página es lo primero que alucina.
2. **La cita sostiene lo que se afirma.** Eso lo deciden los guards.

## Los tres guards, y el error que mató cada uno

### La prensa no confirma política

Una nota sobre una jornada de reciclaje prueba que hubo una jornada, no que
exista un programa. Si se mezclan, el ranking lo encabeza el municipio con mejor
prensa y no el que más hace. Por eso la prensa entra como `indicio` y nunca como
`confirmado`, y el tipo de evidencia viaja pegado a cada hallazgo.

### Una cita puede probar que el tema es de otro

Es el guard que más importa, y el más contraintuitivo. Por **Ley provincial
11.459**, el Certificado de Aptitud Ambiental de un establecimiento de tercera
categoría lo emite **OPDS, no el municipio**. Un portal municipal que explica ese
trámite está diciendo lo contrario de "el municipio fiscaliza".

Sin este guard, la página que **mejor prueba que no le compete** se leería como
que sí. Con él, el estado es `no_compete`, que no es lo mismo que `sin_evidencia`:
uno dice "lo hace la Provincia", el otro dice "no encontramos nada".

La regla es conservadora: si la cita nombra un organismo provincial y no pone al
municipio como sujeto de nada, es `no_compete`. Un convenio de delegación —donde
aparecen los dos— sí confirma.

### Un anuncio no es un hecho

"Se construirá una planta de reciclado" no es una acción ambiental en curso. Las
marcas de hecho ganan sobre las de futuro: *"la planta que se construirá en 2019
hoy funciona"* es un hecho, no un anuncio.

Los tres generan falsos negativos y está bien: **una lista corta y confiable vale
más que una larga que hay que auditar.** Cuando el modelo y el código discrepan,
gana el más conservador.

## Los cuatro estados

| Estado | Qué significa |
|---|---|
| `confirmado` | Hay cita de fuente oficial o normativa |
| `indicio` | Solo prensa: algo pasa, pero no prueba política |
| `no_compete` | La fuente muestra que lo hace otro organismo |
| `sin_evidencia` | No se encontró nada (ADR-0009: el vacío se registra como vacío) |

Al agregar por municipio, `confirmado` gana a `indicio` y `indicio` gana a
`no_compete`: que además haya salido en el diario no degrada una ordenanza.

## Qué NO hace

- **No escribe en `hallazgos_86.sqlite`.** La evidencia de Fase 4 es el activo y
  no se mezcla con lecturas temáticas. Base aparte: `temas_86.sqlite`.
- **No infiere desde la ausencia.** Que un portal no hable de promotores no
  prueba que no los tenga.
- **No reemplaza el ojo.** El `resumen` es lectura del modelo; lo verificado es la
  cita. Por eso la ficha siempre muestra las dos cosas juntas.

## Archivos

| Archivo | Qué tiene |
|---|---|
| `definiciones.py` | Los temas. Configuración pura, sin lógica |
| `rastreo.py` | Entidades. **No** se llama `modelos.py`, `entidades.py` ni `comercial.py`: los tres ya existen en otros paquetes y con `sys.path` se pisan |
| `guardas.py` | Los tres guards: qué puede afirmarse con una cita |
| `cosecha.py` | Qué páginas leer, en tres patas |
| `interrogador.py` | Prompt y verificación |
| `motor_temas.py` | Orquestador, CLI, ficha y cobertura |

## Trampas encontradas armando esto

- **La primera corrida sobre los 86 dio cero en dos de los tres sub-temas.**
  `acciones_ambientales` sacó 23 de 86 y los otros dos quedaron en 0 exacto —
  cero también en `no_compete`, o sea que no llegaba ninguna cita, ni siquiera
  para rechazarla. Eran dos bugs encadenados, los dos en la pata de normativa,
  que es justo donde viven promotores y fiscalización: se bajaba el índice de
  SIBOM en vez de los boletines, y aunque se hubiera bajado el PDF, el recorte a
  4.000 caracteres desde el principio se quedaba con la carátula. Acciones
  funcionaba porque es contenido de portal y no dependía de esa pata.

- **`exige_hecho` empezó puesto solo en acciones.** Estaba mal: *"se implementará
  el programa de promotores en 2027"* tampoco prueba que hoy haya promotores. Las
  tres preguntas son sobre el presente. La bandera sigue existiendo porque un
  sub-tema del tipo "¿hay ordenanza?" no la necesita: la ordenanza ya es el hecho.
- **La cosecha no puede salir del host.** Que un municipio linkee a OPDS no
  convierte a OPDS en fuente municipal, y era la forma más fácil de fabricar un
  falso confirmado de tercera categoría.
- **Las señales van sin tildes.** `normalizar_para_cotejo` las saca de los dos
  lados; escribirlas con tilde funciona igual, pero sin tilde deja claro contra
  qué se cotejan.

## Tests

```
python -m unittest tests.test_temas -v
```

40 tests, sin red y sin IA. Los casos de tercera categoría son los modos
concretos de equivocarse que motivaron el guard.

---

# Plan ambiental: el relevamiento manual

`plan_ambiental.py` importa `data/raw/ambiental/plan_ambiental_86.csv`, el
relevamiento hecho a mano de los 86 municipios. Es la mejor fuente que tiene MIP
sobre el tema —completo, 86 de 86 sin una celda vacía, con fuentes oficiales por
fila— y **manda sobre lo que saque el motor**: eso es lectura de un modelo, esto
es trabajo verificado.

```bash
python src/temas/plan_ambiental.py --importar
python src/temas/plan_ambiental.py --ficha Suipacha
python src/temas/plan_ambiental.py --resumen
```

Vive en la tabla `plan_ambiental` de `temas_86.sqlite`, aparte de
`hallazgos_tema`: un texto redactado por una persona no es una cita literal
verificada contra su fuente, y mezclarlos borraría esa diferencia.

## El CSV venía roto

Todas las filas traen 19 campos y la cabecera nombra 10. Los campos con comas
salieron **sin comillas**, así que una lista como *"industrias láctea, quesera,
agroindustrial y metalmecánica liviana"* se partió en cuatro campos y corrió todo
lo de la derecha. En Suipacha eso dejaba los Puntos Verdes bajo el título
"Fuentes Oficiales", que en realidad era la columna de GIRSU desplazada.

El CSV crudo se versiona **tal cual**. La reparación es código, no una edición a
mano: así es auditable, testeable, y volver a exportar el original no obliga a
rehacer el arreglo.

Se repega con dos señales, y ninguna sola alcanza:

1. Si un campo no cierra oración, el siguiente es su continuación.
2. Si un campo empieza en minúscula, es continuación del anterior.

La segunda existe por Ayacucho: su campo de fiscalización termina en
*"(Mateo Hermanos S.A.)"*, que parece cierre de oración y no lo es. La primera
existe porque hay continuaciones que empiezan con nombre propio (*"La Colina"*,
*"PET"*) y ahí la minúscula no ayuda.

Las URLs son la excepción a las dos: empiezan en minúscula pero no continúan
nada, y arrancan la columna de fuentes aunque el campo anterior haya quedado
abierto.

**Dos invariantes cierran la reparación**: las 86 filas reconstruyen a exactamente
6 campos, y las 86 tienen URL en el sexto. Si alguna vez fallan, el importador se
planta en vez de guardar datos corridos.

## El resumen derivado

El texto es el dato y viaja siempre entero. El `estado` es una lectura derivada
por palabras clave, y existe para una sola cosa: **que los 86 se puedan
comparar**. Un párrafo en prosa no permite ordenar ni filtrar.

| Categoría | Etiquetas | Reparto |
|---|---|---|
| Fiscalización 3ra | mixta / provincial / municipal | 67 / 13 / 5 (+1 sin clasificar) |
| Promotores | cuerpo nombrado | 68 de 86 |
| GIRSU | planta propia, puntos verdes | 51 y 46 de 86 |
| Áreas y arbolado | reserva declarada, plan de arbolado | 21 y 59 de 86 |
| Otras | ordenanza de fitosanitarios | 75 de 86 |

Cuando la etiqueta y el texto no coincidan, **vale el texto**. Por eso el tablero
los muestra juntos y cada etiqueta lleva su glosa: "mixta" sin decir mixta entre
quién y quién no significa nada.

## En el tablero

Pestaña **Ambiental**, y dentro de la ficha de cada municipio. Anda con servidor
(`/api/ambiental`) y también en el HTML estático que genera `generar_html.py`,
donde los datos viajan incrustados.
