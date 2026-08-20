#!/usr/bin/env python3
"""Hooks de sonido para Claude Code.

Reproduce un .wav distinto en cada momento del flujo de trabajo. Claude Code
invoca este script una vez por evento y le pasa el payload del hook por stdin
como JSON.

Mapa de eventos -> sonido
-------------------------
PreToolUse (Write/Edit/Bash/...)  -> empieza.wav    (una sola vez por turno)
Notification (permission_prompt)  -> Solicitud.wav  (se pide una aprobacion)
PostToolUse                       -> Continua.wav   (solo si hubo aprobacion)
Stop                              -> Finalizo.wav
StopFailure (rate_limit)          -> Token.wav
PermissionDenied                  -> (sin sonido, limpia el estado)

"Continua" necesita memoria: PostToolUse se dispara despues de *cualquier*
herramienta, aprobada o no. Por eso el evento de permiso deja una marca en un
archivo de estado y el primer PostToolUse posterior la consume. Sin marca no
suena nada.

El script nunca falla de forma ruidosa: ante cualquier error sale con codigo 0
para no interferir con la sesion de Claude Code.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------

# Carpeta con los .wav. Se puede sobreescribir con la variable de entorno
# CLAUDE_SONIDOS_DIR (util si movesr la carpeta o si la usas en otra maquina).
CARPETA_POR_DEFECTO = r"C:\Users\julia\OneDrive\Documentos\Sonidos de Claudio"

SONIDOS = {
    "empieza": "empieza.wav",
    "solicitud": "Solicitud.wav",
    "continua": "Continua.wav",
    "finalizo": "Finalizo.wav",
    "token": "Token.wav",
}

# Herramientas que cuentan como "ponerse a trabajar". Responder o explicar sin
# tocar archivos no dispara ninguna de estas.
HERRAMIENTAS_DESARROLLO = {
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Bash",
    "BashOutput",
    "KillShell",
}

# Cuanto vale una aprobacion antes de considerarse vencida (segundos). Evita
# que un permiso viejo haga sonar "Continua" mucho despues.
VENTANA_PERMISO_S = 300


# --------------------------------------------------------------------------
# Estado en disco
# --------------------------------------------------------------------------


def _ruta_estado(session_id: str) -> Path:
    carpeta = Path(tempfile.gettempdir()) / "claude_sonidos"
    carpeta.mkdir(parents=True, exist_ok=True)
    seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return carpeta / f"{seguro or 'sesion'}.json"


def _leer_estado(session_id: str) -> dict:
    try:
        with open(_ruta_estado(session_id), encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_estado(session_id: str, estado: dict) -> None:
    ruta = _ruta_estado(session_id)
    try:
        # Escritura atomica: un hook a medio escribir no deja JSON corrupto.
        tmp = ruta.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(estado, fh)
        os.replace(tmp, ruta)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Reproduccion
# --------------------------------------------------------------------------


def _carpeta_sonidos() -> Path:
    return Path(os.environ.get("CLAUDE_SONIDOS_DIR") or CARPETA_POR_DEFECTO)


def _resolver_wav(clave: str) -> Path | None:
    """Devuelve la ruta del .wav, tolerando diferencias de mayusculas."""
    carpeta = _carpeta_sonidos()
    nombre = SONIDOS[clave]

    directo = carpeta / nombre
    if directo.is_file():
        return directo

    # Windows no distingue mayusculas pero Linux/macOS si. Buscamos igual.
    try:
        objetivo = nombre.lower()
        for candidato in carpeta.iterdir():
            if candidato.is_file() and candidato.name.lower() == objetivo:
                return candidato
    except OSError:
        pass
    return None


def _lanzar_desacoplado(argv: list[str]) -> None:
    """Arranca el reproductor sin bloquear ni dejar ventanas abiertas."""
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NO_WINDOW: el sonido sobrevive a este
        # proceso y no parpadea una consola en pantalla.
        kwargs["creationflags"] = 0x00000008 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(argv, **kwargs)


def _interprete_silencioso() -> str:
    """En Windows preferimos pythonw.exe para no abrir consola."""
    ejecutable = sys.executable or "python"
    if sys.platform == "win32":
        pythonw = Path(ejecutable).with_name("pythonw.exe")
        if pythonw.is_file():
            return str(pythonw)
    return ejecutable


def reproducir(clave: str) -> None:
    ruta = _resolver_wav(clave)
    if ruta is None:
        return

    if sys.platform == "win32":
        # winsound en modo asincronico se corta cuando muere el proceso, asi
        # que delegamos en un hijo desacoplado que lo reproduce completo.
        _lanzar_desacoplado([_interprete_silencioso(), __file__, "--reproducir", str(ruta)])
        return

    if sys.platform == "darwin":
        if shutil.which("afplay"):
            _lanzar_desacoplado(["afplay", str(ruta)])
        return

    for programa, args in (
        ("paplay", []),
        ("aplay", ["-q"]),
        ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ):
        if shutil.which(programa):
            _lanzar_desacoplado([programa, *args, str(ruta)])
            return


def _reproducir_bloqueante(ruta: str) -> int:
    """Modo hijo en Windows: suena de principio a fin y termina."""
    try:
        import winsound

        winsound.PlaySound(ruta, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
    except Exception:
        return 1
    return 0


# --------------------------------------------------------------------------
# Logica de eventos
# --------------------------------------------------------------------------


def manejar(payload: dict) -> None:
    evento = payload.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "")
    session_id = str(payload.get("session_id") or "sesion")
    estado = _leer_estado(session_id)

    if evento == "PreToolUse":
        if payload.get("tool_name") not in HERRAMIENTAS_DESARROLLO:
            return
        # prompt_id identifica el turno actual: suena en la primera herramienta
        # de desarrollo del turno y no en las 20 siguientes.
        turno = str(payload.get("prompt_id") or session_id)
        if estado.get("turno_sonado") == turno:
            return
        estado["turno_sonado"] = turno
        _guardar_estado(session_id, estado)
        reproducir("empieza")

    elif evento == "Notification":
        # El matcher ya limita esto a permission_prompt.
        estado["permiso_aprobado_pendiente"] = time.time()
        _guardar_estado(session_id, estado)
        reproducir("solicitud")

    elif evento == "PostToolUse":
        marca = estado.get("permiso_aprobado_pendiente")
        if not isinstance(marca, (int, float)):
            return
        estado["permiso_aprobado_pendiente"] = None
        _guardar_estado(session_id, estado)
        if time.time() - marca <= VENTANA_PERMISO_S:
            reproducir("continua")

    elif evento == "PermissionDenied":
        # Rechazaste el permiso: la marca se descarta sin sonar "Continua".
        estado["permiso_aprobado_pendiente"] = None
        _guardar_estado(session_id, estado)

    elif evento == "Stop":
        estado["permiso_aprobado_pendiente"] = None
        estado["turno_sonado"] = None
        _guardar_estado(session_id, estado)
        reproducir("finalizo")

    elif evento == "StopFailure":
        # El matcher ya limita esto a rate_limit.
        estado["permiso_aprobado_pendiente"] = None
        estado["turno_sonado"] = None
        _guardar_estado(session_id, estado)
        reproducir("token")


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--reproducir":
        return _reproducir_bloqueante(sys.argv[2])

    try:
        crudo = sys.stdin.read()
    except Exception:
        crudo = ""

    try:
        payload = json.loads(crudo) if crudo.strip() else {}
    except ValueError:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    try:
        manejar(payload)
    except Exception:
        # Un hook de sonido jamas debe romper la sesion.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
