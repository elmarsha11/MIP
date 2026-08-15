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
3. **Prensa local**, si se pide con `--con-prensa`.

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
