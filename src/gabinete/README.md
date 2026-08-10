# Motor de gabinete — quién gobierna cada municipio

> Fase 3 encontró **dónde** mirar. Fase 4 reportó **qué dicen** los portales.
> Esto responde **quién está a cargo**, que es a quién hay que ir a ver.

## Por qué no se saca del resumen de un buscador

Poner *"secretarías municipales Chascomús"* en Google devuelve una lista completa
y prolija de 8 secretarías con nombre y apellido. El dato es mayormente real. El
problema es otro.

El 2026-08-09 se comparó esa lista contra el **Boletín Oficial del 16/07/2026**:

| Secretaría | Buscador (vía Instagram municipal) | Boletín Oficial |
|---|---|---|
| Gobierno | Cipriano Pérez del Cerro | ✅ igual |
| Seguridad Ciudadana | Mariela Moscarella | ✅ igual |
| Salud Pública | Marcela Arias | ✅ igual |
| Desarrollo Social | Leandro Bordalecou | ✅ igual |
| Turismo, Deportes y Cultura | Julieta Spina | ✅ igual |
| Hacienda | Marcelo Teil**l**eche | Marcelo Teil**e**che |
| **Obras, Servicios y Ambiente** | **Jorge Marino** | **Lucas Funes** |
| Modernización | Pablo Nápoli | no figura en los boletines leídos |

En ese boletín *"Marino"* aparece **0 veces** y *"Funes"* **11**. El decreto es
explícito:

> *"El presente Decreto será refrendado por el Secretario de Obras, Servicios
> Públicos y Ambiente (**Lucas Funes**)."*

Seis de ocho coincidían. La séptima habría hecho entrar a una reunión nombrando
al secretario equivocado. **Ese es el único costo que importa**, y no se descubre
mirando más fuerte el resumen: hace falta la fuente.

Aparte: el propio boletín escribe el mismo apellido de tres formas (*Cipriano
Pérez / Cipiano Pérez / Cipriano Péres*). Cualquier fuente necesita normalización.

## Qué es fuente y qué no

El Instagram oficial del municipio **sí es fuente citable**: es un canal del
municipio y tiene fecha. Lo que no es fuente es el resumen de la IA, que no dice
de qué publicación salió ni de cuándo. Ahí el buscador sirve para **encontrar**
la fuente, nunca para ser la fuente.

Por eso las fuentes están ordenadas por dureza, y la confianza sale de ahí:

| Fuente | Confianza | Por qué |
|---|---|---|
| `boletin_oficial` | Alta | Decreto publicado, con fecha, que nombra a quien lo refrenda |
| `portal` | Media | Oficial, pero una nota puede ser vieja y no siempre está fechada |
| `red_oficial` | Baja | Del municipio, pero lo más volátil y lo más difícil de fechar |

## Uso

```bash
python src/gabinete/motor_gabinete.py --municipio Chascomus
python src/gabinete/motor_gabinete.py --all
python src/gabinete/motor_gabinete.py --ficha Chascomus     # no llama a la IA
python src/gabinete/motor_gabinete.py --cobertura           # no llama a la IA
```

## La verificación, en tres pasos

1. **La cita existe literal** en el boletín — ADR-0014, igual que Fase 4.
2. **El nombre está adentro de la cita** — handoff §7: verificar el valor, no
   solo la cita.
3. **El nombre no bautiza un edificio** — `nombres.py`. Esto es nuevo.

El paso 3 no existía en ningún otro módulo de MIP y acá es imprescindible:

> *"Centro de Salud «Intendente Pedro Carossi»"*

Eso es un CAPS con el nombre de un intendente anterior. La cita es literal y el
nombre está adentro: **pasa los pasos 1 y 2 sin problema**. `nombres.py` mira el
contexto y descarta los nombres precedidos de palabras que bautizan cosas
(Centro, Escuela, Calle, Hospital, Plaza…), con o sin título intercalado
(*"Escuela Doctor René Favaloro"*), y los que están entre comillas.

Genera falsos negativos y está bien: un intendente de menos se completa a mano;
un intendente equivocado se lleva puesta la credibilidad de la base entera.

## Por qué un modelo y no una expresión regular

Chascomús firma *"será refrendado por el Secretario de Obras (Lucas Funes)"*.
Castelli publica 146.000 caracteres **sin usar esa fórmula**. El formato varía por
municipio; la pregunta no. Es exactamente el reparto de ADR-0014: la IA lee, el
código verifica.

## El recorte, que costó dos bugs

Los dos últimos boletines de Chascomús son **773.000 caracteres**. Se manda al
modelo un recorte de 60.000, y armarlo bien fue la mitad del trabajo:

1. **Un boletín trae ~70 firmas de apenas 5 o 6 personas.** Sin deduplicar, el
   recorte se llenaba de Pérez del Cerro repetido y cortaba antes de llegar a
   Moscarella, que aparece 2 veces en todo el documento. Se perdían **3 de 8
   secretarías**.
2. **La pista `"Secretario de"` está adentro de la fórmula de refrendo.** El pase
   de contexto volvía a traer cada firma con 700 caracteres de decreto alrededor,
   fusionadas en un tramo único que la deduplicación ya no reconocía. Ahora el
   pase de contexto saltea lo que el pase de firmas ya cubrió.

## Cobertura

**65 de los 86 municipios publican boletines en SIBOM** (medido el 2026-08-09).
Los otros 21 están registrados pero no publicaron nunca — Navarro y Ayacucho
entre ellos. Para esos hay que ir por el portal o la red oficial: **no se
inventa**, y `--cobertura` los lista por nombre.

El intendente rara vez firma con su nombre en el boletín: en Chascomús *"Gastón"*
aparece una sola vez en 773.000 caracteres, y encima referido a otra persona
(SULLING Gastón, un chofer). Para el intendente la fuente natural es el portal,
donde ya se midió que **48 de 84 municipios** lo nombran en el texto que MIP
descarga.

## Archivos

| Archivo | Qué tiene |
|---|---|
| `sibom.py` | Acceso al Boletín Oficial: índice, PDF, texto. Cachea solo aciertos |
| `nombres.py` | El guard: ¿este nombre es una persona en el cargo o un edificio? |
| `lector.py` | Recorte, prompt y verificación |
| `autoridades.py` | Entidades. **No** se llama `modelos.py`, `entidades.py` ni `comercial.py`: los tres ya existen en otros paquetes y con `sys.path` se pisan |
| `motor_gabinete.py` | Orquestador, CLI, ficha y cobertura |

## Dependencia

Necesita `pypdf` para leer los boletines:

```bash
python -m pip install pypdf
```
