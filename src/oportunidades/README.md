# Motor comercial — qué le vende UDS a cada municipio

> Fase 3 encontró **dónde** mirar. Fase 4 reportó **qué dicen** los portales.
> Esto responde **qué le falta** a cada municipio y qué producto de UDS lo resuelve.

## Por qué existe

MIP registra bien lo que hay y casi nada de lo que falta. Al 2026-08-09:

| Variable | "si" | "no" | sin dato |
|---|---:|---:|---:|
| `boletin_oficial` | 86 | 0 | 0 |
| `pago_online_tasas` | 39 | **0** | 47 |
| `turnos_salud_online` | 11 | 7 | 68 |

Para UDS **el prospecto es la ausencia**. Un municipio con 86/86 en boletín oficial
no le dice nada al equipo comercial; uno donde hay que llamar por teléfono para
sacar un turno, sí.

Peor: la evidencia del proceso manual **ya estaba en la base** y se perdía. Siete
municipios tenían `canal_turnos_salud = telefono` verificado con cita, pero
`turnos_salud_online = no_verificable`, así que caían en el balde de "sin datos"
en vez de la lista de prospectos. Navarro es el caso: *"CONSULTORIOS EXTERNOS
2272-400663"* estaba capturado desde el principio.

## Qué hace

Relee el texto de las páginas buscando **fricción**: una frase que pruebe que hoy
alguien tiene que llamar, ir, esperar o hacer a mano algo que un sistema
resolvería. Cada oportunidad sale con su cita literal verificada.

```bash
python src/oportunidades/motor.py --municipio Navarro   # analizar uno
python src/oportunidades/motor.py --all                 # los 86
python src/oportunidades/motor.py --ficha Navarro       # ficha comercial
python src/oportunidades/motor.py --ranking             # los 86 por potencial
```

Las dos últimas no llaman a la IA: leen lo ya analizado.

## La regla que lo sostiene

**La IA propone, el código verifica** (ADR-0014), en dos pasos y no en uno:

1. **La cita existe literal** en la página. Igual que Fase 4.
2. **La cita prueba fricción.** Esto es nuevo y es lo que hace útil al módulo.

El paso 2 nació de la primera corrida: sobre Navarro devolvió 7 oportunidades y
solo 1 servía. El modelo estaba tratando *"el texto no dice que sea digital"*
como si fuera fricción, y citaba cosas como *"debés registrarte en el siguiente
link: Registrarme"* — que es un sistema **andando**, o sea lo contrario de una
oportunidad. Inferir desde la ausencia es justamente lo que ADR-0009 prohíbe.

`friccion.py` exige que la cita contenga una acción manual y descarta la que
muestre un canal digital. Con el guard puesto, Navarro pasó de 7 a 3.

Genera falsos negativos —una fricción redactada raro se pierde— y está bien:
**el costo de un prospecto falso es una reunión perdida.** Una lista corta y
confiable vale más que una larga que hay que auditar.

## Niveles de fricción

Ordenan el trabajo comercial. Aplanarlos convierte la lista en ruido.

| Nivel | Qué prueba la cita | Ejemplo real |
|---|---|---|
| `alta` | Hay que ir, llamar o esperar sí o sí | *"dirigirse a la Mesa de Entradas del Hospital"* (Ayacucho) |
| `media` | Canal manual publicado, sin digital a la vista | *"Por ventanilla en los bancos"* (Pinamar) |
| `baja` | Indicio suelto, sin proceso descrito | un teléfono en un directorio |

El puntaje pesa 5/2/1: **una fricción alta probada vale más que tres indicios
sueltos.** Si fuera lineal, el equipo comercial visitaría al municipio equivocado.

Cuando el modelo y el código discrepan, gana el más conservador de los dos.

## Qué NO hace

- **No escribe en `hallazgos_86.sqlite`.** La evidencia de Fase 4 es el activo y no
  se mezcla con interpretación comercial. Base aparte: `oportunidades_86.sqlite`.
- **No aporta datos nuevos.** Solo reinterpreta páginas ya descargadas.
- **No reemplaza el ojo.** El `problema` y la `friccion` son lectura del modelo;
  lo verificado es la cita. Por eso la ficha siempre muestra las dos cosas juntas.

## Por qué corre con DeepSeek y no con Gemini

Es interpretación sobre evidencia ya probada, no sourcing: barata de re-correr
mientras se afina el prompt, y sin el techo de 200 llamadas diarias de Gemini. Los
86 salen en una corrida y cuesta centavos.

Fase 4 sigue siendo de Gemini — ver `docs/VALIDACION_DEEPSEEK_2026-08-09.md`, donde
DeepSeek encontró 42% menos evidencia. Acá la tarea es otra: texto corto, juicio
acotado, y con el guard de `friccion.py` encima.

## Archivos

| Archivo | Qué tiene |
|---|---|
| `catalogo.py` | Los productos de UDS y las señales que delatan cada oportunidad |
| `friccion.py` | El guard: ¿esta cita prueba un proceso manual? |
| `detector.py` | Prompt y verificación |
| `comercial.py` | Entidades. **No** se llama `modelos.py` ni `entidades.py`: los dos ya existen en otros paquetes y con `sys.path` se pisan |
| `paginas.py` | Caché del texto. Solo guarda aciertos |
| `motor.py` | Orquestador, CLI, ficha y ranking |

## Trampas encontradas armando esto

- **`entidades.py` rompió Fase 6 sin tocar Fase 6.** El módulo homónimo de
  `src/territorio/` quedó tapado por el nuevo. Es la colisión que el handoff ya
  documentaba, mordida de nuevo. De ahí `comercial.py`.
- **Una cita puede probar lo contrario de lo que el modelo dice.** En Pinamar la
  cita de reclamos incluía *"Sistema Web de Reclamos CCA"*: ya lo tienen. Los
  patrones de `_YA_DIGITAL` ganan sobre los de fricción.
- **El techo de 12 oportunidades invitaba a rellenar.** Hubo que pedir
  explícitamente 2 sólidas antes que 8 flojas.
