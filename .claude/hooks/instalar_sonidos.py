#!/usr/bin/env python3
r"""Instala (o desinstala) los hooks de sonido en el settings.json de Claude Code.

Uso tipico, desde la raiz del proyecto:

    python .claude\hooks\instalar_sonidos.py            # instala global
    python .claude\hooks\instalar_sonidos.py --probar   # prueba los 5 sonidos
    python .claude\hooks\instalar_sonidos.py --quitar   # desinstala

Por defecto escribe en el settings.json global (~/.claude/settings.json) para
que los sonidos funcionen en todos los proyectos. Con --proyecto escribe en
.claude/settings.json de este repo.

Es idempotente: antes de escribir borra cualquier version previa de estos
mismos hooks, asi que correrlo dos veces no duplica sonidos. Tambien avisa si
quedaron instalados en los dos ambitos a la vez (eso si haria sonar todo doble).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT_HOOK = AQUI / "sonidos_claude.py"

# Eventos que registramos, con su matcher. None = sin matcher (todos los casos).
EVENTOS = [
    ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit|Bash"),
    ("Notification", "permission_prompt"),
    ("PostToolUse", None),
    ("PermissionDenied", None),
    ("Stop", None),
    ("StopFailure", "rate_limit"),
]


def ruta_settings(ambito: str) -> Path:
    if ambito == "proyecto":
        return AQUI.parent / "settings.json"
    return Path.home() / ".claude" / "settings.json"


def leer_json(ruta: Path) -> dict:
    if not ruta.is_file():
        return {}
    texto = ruta.read_text(encoding="utf-8").strip()
    if not texto:
        return {}
    try:
        datos = json.loads(texto)
    except ValueError as exc:
        raise SystemExit(
            f"ERROR: {ruta} no es JSON valido ({exc}).\n"
            "Corregilo a mano antes de instalar; si no, Claude Code ignora "
            "todo el archivo en silencio."
        )
    if not isinstance(datos, dict):
        raise SystemExit(f"ERROR: {ruta} deberia contener un objeto JSON.")
    return datos


def es_hook_nuestro(entrada: dict) -> bool:
    """Reconoce nuestros hooks por la ruta del script, sin importar el matcher."""
    for hook in entrada.get("hooks", []):
        if not isinstance(hook, dict):
            continue
        texto = " ".join(
            [str(hook.get("command", ""))] + [str(a) for a in hook.get("args", [])]
        )
        if "sonidos_claude.py" in texto:
            return True
    return False


def quitar_hooks(config: dict) -> int:
    """Saca nuestros hooks de la config. Devuelve cuantos saco."""
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return 0

    quitados = 0
    for evento in list(hooks):
        entradas = hooks.get(evento)
        if not isinstance(entradas, list):
            continue
        conservadas = []
        for entrada in entradas:
            if isinstance(entrada, dict) and es_hook_nuestro(entrada):
                quitados += 1
            else:
                conservadas.append(entrada)
        if conservadas:
            hooks[evento] = conservadas
        else:
            # No dejamos listas vacias dando vueltas.
            del hooks[evento]

    if not hooks:
        config.pop("hooks", None)
    return quitados


def agregar_hooks(config: dict, interprete: str) -> None:
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit("ERROR: la clave 'hooks' del settings.json no es un objeto.")

    for evento, matcher in EVENTOS:
        # Forma exec (command + args): Claude Code lanza el ejecutable directo,
        # sin pasar por un shell. Asi la ruta con espacios funciona igual en
        # PowerShell que en Git Bash.
        entrada: dict = {
            "hooks": [
                {
                    "type": "command",
                    "command": interprete,
                    "args": [str(SCRIPT_HOOK)],
                    "timeout": 10,
                }
            ]
        }
        if matcher is not None:
            entrada["matcher"] = matcher

        entradas = hooks.setdefault(evento, [])
        if not isinstance(entradas, list):
            raise SystemExit(f"ERROR: hooks.{evento} deberia ser una lista.")
        entradas.append(entrada)


def escribir(ruta: Path, config: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.is_file():
        sello = datetime.now().strftime("%Y%m%d-%H%M%S")
        respaldo = ruta.with_name(f"{ruta.name}.bak-{sello}")
        shutil.copy2(ruta, respaldo)
        print(f"Respaldo: {respaldo}")

    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(ruta)


def avisar_duplicados(ambito_escrito: str) -> None:
    otro = "proyecto" if ambito_escrito == "global" else "global"
    ruta = ruta_settings(otro)
    config = leer_json(ruta) if ruta.is_file() else {}
    copia = json.loads(json.dumps(config))
    if quitar_hooks(copia) > 0:
        print()
        print(f"AVISO: tambien hay hooks de sonido en el settings.json {otro}:")
        print(f"       {ruta}")
        print("       Los dos ambitos se suman y cada sonido se escucharia dos veces.")
        print(f"       Sacalos con:  python {Path(__file__).name} --quitar --{otro}")


def verificar_wavs() -> None:
    sys.path.insert(0, str(AQUI))
    import sonidos_claude as sc  # noqa: E402

    carpeta = sc._carpeta_sonidos()
    print(f"Carpeta de sonidos: {carpeta}")
    if not carpeta.is_dir():
        print("  AVISO: la carpeta no existe. Los hooks quedan instalados pero mudos.")
        print("  Podes apuntar a otra carpeta con la variable CLAUDE_SONIDOS_DIR.")
        return

    faltantes = [c for c in sc.SONIDOS if sc._resolver_wav(c) is None]
    for clave, nombre in sc.SONIDOS.items():
        estado = "FALTA" if clave in faltantes else "ok"
        print(f"  [{estado:>5}] {nombre}")
    if faltantes:
        print("  AVISO: los sonidos faltantes simplemente no suenan; nada se rompe.")


def probar_sonidos() -> int:
    """Reproduce los cinco sonidos, uno por uno, para verificar el audio."""
    import time

    sys.path.insert(0, str(AQUI))
    import sonidos_claude as sc  # noqa: E402

    print(f"Carpeta de sonidos: {sc._carpeta_sonidos()}")
    print(f"Plataforma: {sys.platform}")
    print()

    fallas = 0
    for clave, nombre in sc.SONIDOS.items():
        ruta = sc._resolver_wav(clave)
        if ruta is None:
            print(f"  [FALTA] {nombre}")
            fallas += 1
            continue
        print(f"  [suena] {nombre}")
        sc.reproducir(clave)
        time.sleep(2)

    print()
    if fallas:
        print(f"{fallas} sonido(s) no se encontraron.")
        return 1
    print("Si escuchaste los cinco, el audio esta bien configurado.")
    return 0


def simular_flujo() -> int:
    """Corre el script como lo hace Claude Code: proceso aparte y JSON por stdin."""
    secuencia = [
        ("PreToolUse", {"tool_name": "Edit"}, "empieza"),
        ("PreToolUse", {"tool_name": "Bash"}, "(silencio: ya sono en este turno)"),
        ("PreToolUse", {"tool_name": "Read"}, "(silencio: Read no es desarrollo)"),
        ("Notification", {}, "Solicitud"),
        ("PostToolUse", {"tool_name": "Bash"}, "Continua"),
        ("PostToolUse", {"tool_name": "Bash"}, "(silencio: no hubo permiso nuevo)"),
        ("Stop", {}, "Finalizo"),
        ("StopFailure", {}, "Token"),
    ]

    print("Simulando un turno completo (proceso real, stdin JSON):\n")
    fallas = 0
    for evento, extra, esperado in secuencia:
        payload = {
            "hook_event_name": evento,
            "session_id": "simulacion",
            "prompt_id": "turno-simulado",
        }
        payload.update(extra)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0 and not proc.stdout and not proc.stderr
        if not ok:
            fallas += 1
        marca = "ok " if ok else "FALLA"
        print(f"  [{marca}] {evento:<16} -> {esperado}")
        if not ok:
            print(f"          rc={proc.returncode} out={proc.stdout!r} err={proc.stderr!r}")

    print()
    if fallas:
        print(f"{fallas} evento(s) devolvieron algo inesperado.")
        return 1
    print("Los 8 eventos salieron limpios (codigo 0, sin ruido en stdout/stderr).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ambito = parser.add_mutually_exclusive_group()
    ambito.add_argument("--global", dest="global_", action="store_true", help="settings.json global (por defecto)")
    ambito.add_argument("--proyecto", action="store_true", help="settings.json de este repo")
    parser.add_argument("--quitar", action="store_true", help="desinstala los hooks")
    parser.add_argument("--probar", action="store_true", help="reproduce los 5 sonidos")
    parser.add_argument("--simular", action="store_true", help="simula un turno sin instalar nada")
    parser.add_argument("--interprete", default=sys.executable, help="ejecutable de Python para los hooks")
    args = parser.parse_args()

    if args.probar:
        return probar_sonidos()
    if args.simular:
        return simular_flujo()

    if not SCRIPT_HOOK.is_file():
        raise SystemExit(f"ERROR: no encuentro {SCRIPT_HOOK}")

    destino = "proyecto" if args.proyecto else "global"
    ruta = ruta_settings(destino)
    config = leer_json(ruta)

    quitados = quitar_hooks(config)
    if args.quitar:
        if quitados == 0:
            print(f"No habia hooks de sonido en {ruta}. Sin cambios.")
            return 0
        escribir(ruta, config)
        print(f"Quitados {quitados} hooks de sonido de {ruta}")
        return 0

    agregar_hooks(config, args.interprete)
    escribir(ruta, config)

    if quitados:
        print(f"Reemplazados {quitados} hooks previos.")
    print(f"Instalados {len(EVENTOS)} hooks de sonido en {ruta}")
    print(f"Interprete: {args.interprete}")
    print()
    verificar_wavs()
    avisar_duplicados(destino)
    print()
    print("Reinicia Claude Code (o abri /hooks una vez) para que tome los cambios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
