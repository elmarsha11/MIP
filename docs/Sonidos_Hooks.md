# Hooks de sonido para Claude Code

Reproducen un `.wav` distinto en cada momento del flujo de trabajo.

## Instalacion

Desde la raiz del proyecto, en tu maquina Windows:

```
python .claude\hooks\instalar_sonidos.py
```

Escribe en el `settings.json` global (`C:\Users\julia\.claude\settings.json`), asi
los sonidos funcionan en todos tus proyectos y no solo en MIP. Hace un respaldo
con fecha antes de tocar nada y conserva lo que ya tenias configurado.

Despues **reinicia Claude Code** (o abri `/hooks` una vez) para que tome los cambios.

Para verificar que el audio anda, antes o despues de instalar:

```
python .claude\hooks\instalar_sonidos.py --probar
```

Reproduce los cinco sonidos con dos segundos de pausa. Si los escuchas todos,
esta listo.

## Cuando suena cada uno

| Sonido | Evento de Claude Code | Cuando lo escuchas |
|---|---|---|
| `empieza.wav` | `PreToolUse` (`Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `Bash`) | Claude se pone a trabajar: edita archivos, escribe codigo o corre comandos. **Una sola vez por turno**, en la primera herramienta. Si solo te responde o explica algo, no suena. |
| `Solicitud.wav` | `Notification` (`permission_prompt`) | Te aparece un pedido de aprobacion para editar un archivo o correr un comando. |
| `Continua.wav` | `PostToolUse` | Aprobaste un permiso y la herramienta ya corrio. Solo suena si antes hubo un permiso; en acciones que no requieren aprobacion, no. |
| `Finalizo.wav` | `Stop` | Claude termino de responder y queda esperando tu proximo mensaje. |
| `Token.wav` | `StopFailure` (`rate_limit`) | Se corto el turno porque te quedaste sin limite de uso. |

## Como funciona "Continua"

`PostToolUse` se dispara despues de *cualquier* herramienta, haya requerido
aprobacion o no. Para que `Continua.wav` suene solo tras un permiso aprobado,
hace falta memoria entre eventos:

1. Cuando aparece el pedido de permiso, el hook de `Notification` deja una marca
   con la hora en un archivo de estado.
2. El primer `PostToolUse` posterior encuentra la marca, la consume y recien ahi
   reproduce `Continua.wav`.
3. Sin marca no suena nada. La marca se usa **una sola vez**.

La marca tambien se descarta si rechazas el permiso (`PermissionDenied`), si
termina el turno (`Stop`) o si pasaron mas de 5 minutos. Asi un permiso viejo no
dispara el sonido mucho despues.

El estado vive en `%TEMP%\claude_sonidos\<session_id>.json`, un archivo por
sesion, asi dos ventanas de Claude Code abiertas al mismo tiempo no se pisan.

## Por que "Empieza" suena una vez por turno

El hook usa el `prompt_id` del turno para no repetirse. Si Claude edita quince
archivos seguidos escuchas `empieza.wav` una vez, no quince. En el turno
siguiente vuelve a sonar.

Si preferis escucharlo en **cada** herramienta, borra estas tres lineas de
`.claude/hooks/sonidos_claude.py`, dentro de la rama `PreToolUse`:

```python
turno = str(payload.get("prompt_id") or session_id)
if estado.get("turno_sonado") == turno:
    return
```

## Configuracion

**Carpeta de sonidos.** Por defecto:

```
C:\Users\julia\OneDrive\Documentos\Sonidos de Claudio
```

Para usar otra, defini la variable de entorno `CLAUDE_SONIDOS_DIR`. Los nombres
de archivo (`empieza.wav`, `Solicitud.wav`, `Continua.wav`, `Finalizo.wav`,
`Token.wav`) se buscan sin distinguir mayusculas.

**Que cuenta como "herramienta de desarrollo".** Se define en
`HERRAMIENTAS_DESARROLLO`, arriba de `sonidos_claude.py`. Si agregas o sacas
alguna, actualiza tambien el `matcher` de `PreToolUse` en `instalar_sonidos.py`
y volve a instalar.

**Ventana del permiso.** `VENTANA_PERMISO_S`, por defecto 300 segundos.

## Desinstalar

```
python .claude\hooks\instalar_sonidos.py --quitar
```

Saca solo estos hooks y deja intacto el resto del `settings.json`.

## Notas

- **Nunca rompe la sesion.** Ante cualquier error (falta un `.wav`, no existe la
  carpeta, el estado quedo corrupto) el script sale con codigo 0 y en silencio.
- **No agrega demora.** El `.wav` se reproduce en un proceso desacoplado: el hook
  larga el sonido y termina enseguida, sin bloquear a Claude Code ni abrir
  ventanas de consola.
- **No lo instales en los dos ambitos.** Si esta en el `settings.json` global y en
  el del proyecto a la vez, los hooks se suman y cada sonido se escucha dos
  veces. El instalador te avisa si detecta esa situacion.
- **Multiplataforma.** En Windows usa `winsound`; en Linux `paplay`, `aplay` o
  `ffplay`; en macOS `afplay`.

## Tests

```
python -m unittest tests.test_sonidos_hooks -v
```

23 tests que cubren el mapeo de eventos, la memoria del permiso, el
aislamiento entre sesiones y los casos de error. No reproducen audio.

Para ver la secuencia de un turno completo sin instalar nada:

```
python .claude\hooks\instalar_sonidos.py --simular
```
