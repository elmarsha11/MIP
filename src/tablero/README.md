# src/tablero — La cara de MIP

```bash
python src/tablero/servidor.py
```

Abre `http://127.0.0.1:8765` en el navegador. Nada que instalar.

## Por qué sin framework

Está hecho con la biblioteca estándar de Python. Sin FastAPI, sin Flask, sin
npm, sin CDN. Cualquier PC con Python lo corre sin `pip install`.

Para una herramienta confidencial que tiene que ser portable, eso vale más que
la comodidad de un framework: no hay cadena de dependencias de terceros, no hay
build, y no se carga un solo recurso desde internet.

## Seguridad

- **Escucha solo en 127.0.0.1.** No es accesible desde la red aunque la máquina
  esté en una wifi compartida.
- **Las bases se abren en modo lectura** (`mode=ro`). El tablero no puede
  corromper el conocimiento.
- **Las acciones son una lista blanca cerrada.** El nombre que llega por HTTP
  nunca se convierte en un comando: se usa para elegir de un diccionario fijo.
  Los subprocesos corren con `shell=False` y el municipio va como argumento.
- **No hay login**, porque no hace falta: solo escucha local. Publicarlo para el
  equipo es otra decisión, y necesita hosting privado y autenticación.

## Las seis vistas

| Vista | Para qué |
|---|---|
| **Panel** | Estado general en ocho números |
| **Municipios** | Los 86, con filtros. Click en una fila abre su ficha |
| **Mapa de turnos** | Quién resolvió, quién no, de quién no sabemos |
| **Impacto** | Costo social y techo de precio, con sus advertencias |
| **Revisión** | Lo que necesita ojo humano antes de una propuesta |
| **Acciones** | Botones que lanzan el motor, con salida en vivo |

## Lo que lo diferencia de un dashboard cualquiera

**Ningún número viaja sin su evidencia.** Cada dato en pantalla se puede abrir
hasta la cita textual, la URL, la fecha y el nivel de confianza. Un Power BI
muestra un número lindo; no muestra de dónde salió ni cuándo se verificó.

Frente a un Tribunal de Cuentas o a CAF, esa diferencia es todo el producto.

**El vacío se ve.** 63 municipios sin datos de turnos aparecen listados como
tales, no escondidos ni promediados. ADR-0009.

**Las advertencias van pegadas al número.** La vista de Impacto no muestra la
cifra sin decir, arriba y en rojo, que es una estimación con supuestos sin
fuente y que no es ahorro fiscal.

## Los botones no calculan nada

Lanzan los mismos comandos que se correrían a mano, en un proceso aparte, y
muestran su salida en vivo. El motor sigue siendo la verdad y se puede correr
sin tablero.

Si el tablero calculara por su cuenta, tendríamos dos MIP que algún día darían
resultados distintos.

## Deuda conocida

- No hay login ni usuarios: hoy no hace falta porque es local.
- La salida de una tarea se pierde al cerrar el servidor.
- No hay gráficos. Las tablas con evidencia son más útiles que un gráfico sin
  fuente, pero para una presentación a un intendente van a hacer falta.
- Falta la vista de Fase 5 (madurez), que todavía no existe como motor.
