# src/extraction - Fase 4: Extraccion verificada

Fase 3 encontro **donde mirar**. Fase 4 lee esas paginas y reporta **que dicen**,
con los 5 sellos: URL, fecha, fragmento literal, tipo de fuente y confianza.

```bash
python src/extraction/extraction_engine.py --municipio Navarro
python src/extraction/extraction_engine.py --all
python src/extraction/extraction_engine.py --municipio Navarro --sin-ia   # sin gastar cuota
python -m unittest discover -s tests -v
```

## El principio: la IA propone, el codigo verifica

Gemini nunca aporta un dato. Aporta un **valor candidato** y una **cita textual**
del texto que se le dio. Despues, `cita_esta_en_fuente()` comprueba que esa cita
exista literalmente en la fuente. Si no existe, el hallazgo se descarta y la
variable queda `no_verificable`.

Una alucinacion no puede sobrevivir a eso: para pasar, tendria que inventar una
cita que ademas este textualmente en la pagina, y eso ya no es alucinar.

Ver ADR-0014.

## Modulos

| Archivo | Que hace |
|---|---|
| `modelos.py` | `Hallazgo` con los 5 sellos. ADR-0009 como validadores que levantan excepcion |
| `fetcher.py` | Descarga las paginas que Fase 3 ya tipifico y valido. No busca ni adivina |
| `gemini_client.py` | Cuota diaria persistida, cache en disco, cadena de modelos con respaldo |
| `extractor.py` | Prompt, capa deterministica y verificacion de citas |
| `extraction_engine.py` | Orquestador, CLI y persistencia |

## Tres capas de respuesta

1. **Deterministica, sin IA.** Si Fase 3 valido una URL de tipo `licitaciones`
   con su fragmento, el municipio publica licitaciones. Preguntarselo a un
   modelo seria peor: la evidencia ya existe y es mas dura.
2. **IA verificada.** Lo que el tipo de URL no prueba. El caso testigo es
   `turnos_salud_online`: tener una seccion de salud **no** es tener turnero
   online, y esa distincion hay que leerla.
3. **Vacio honesto.** Todo lo demas queda `no_verificable` con confianza 0%.

## Cuota de Gemini (plan gratuito)

- **Una llamada por municipio.** 86 por corrida completa, contra un tope de 200
  diarias configurado en `gemini_client.py`. Muy por debajo del limite real.
- **Cache por hash del prompt.** Re-correr un municipio cuyo portal no cambio
  no gasta ni una llamada.
- **Contador diario persistido en disco.** Si el proceso se corta y se relanza,
  no se resetea la cuenta y no se pasa del limite.
- Al llegar al tope corta con un mensaje claro y **guarda lo procesado**. Se
  sigue al dia siguiente desde donde quedo.

## La clave de API

Se lee de la variable de entorno `GEMINI_API_KEY` y, si no esta, de
`credenciales.txt`. Ese archivo esta en `.gitignore` y nunca se versiona.

Para no dejarla escrita en una carpeta que sincroniza con la nube:

```bash
setx GEMINI_API_KEY "tu-clave"
```

## Cosas no obvias

- **Los modelos se retiran.** El 2026-08-07 `gemini-2.5-flash` dejo de estar
  disponible para cuentas nuevas. Por eso hay una cadena de modelos con
  respaldo y se prefieren los alias `-latest`. MIP tiene que seguir andando solo.
- **`modelos.py`, no `schemas.py`.** Fase 3 ya tiene un `schemas.py` y ambos
  directorios estan en el path; con el mismo nombre se pisaban.
- **Cada hallazgo registra que modelo lo produjo.** Si manana un modelo resulta
  malo, se sabe exactamente que datos revisar.
- **`--sin-ia` corre todo menos la llamada al modelo.** Sirve para probar la
  lectura de paginas sin gastar cuota.

## Estado

11 municipios procesados, 50% de variables con evidencia verificada,
**0 citas rechazadas**. Encontro turnos de salud online reales en Arrecifes y
Chacabuco, citando el texto del portal.

## Deuda conocida

- Falta el ticket de cierre: contrastar los 86 contra el Gold Standard y medir
  en cuantos coincide el motor con la persona que lo hizo a mano.
- Se lee una pagina por tipo. Un segundo nivel de navegacion subiria la cobertura.
- `no` casi no aparece: el modelo rara vez encuentra evidencia explicita de
  ausencia. Es correcto segun ADR-0009, pero para el Gold Standard "no tiene
  turnos online" es un dato valioso que hoy queda como `no_verificable`.
