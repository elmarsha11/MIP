"""
Tablero - Acciones que disparan el motor.

Los botones del tablero no calculan nada: lanzan los mismos comandos que se
correrian a mano, en un proceso aparte, y muestran su salida en vivo.

Se hace asi a proposito. El motor sigue siendo la verdad y se puede correr sin
tablero; el tablero es una cara, no una implementacion paralela. Si algun dia
las dos formas dieran resultados distintos, tendriamos dos MIP.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Acciones permitidas. Lista blanca cerrada: el nombre que llega por HTTP nunca
# se convierte en un comando. Se usa para elegir de aca.
ACCIONES = {
    "descubrir_municipio": {
        "titulo": "Redescubrir URLs del municipio",
        "comando": [sys.executable, "-u", "src/discovery/discovery_engine.py", "--municipio"],
        "requiere_municipio": True,
        "minutos_estimados": 1,
    },
    "extraer_municipio": {
        "titulo": "Volver a leer y extraer variables",
        "comando": [sys.executable, "-u", "src/extraction/extraction_engine.py", "--municipio"],
        "requiere_municipio": True,
        "minutos_estimados": 1,
        "consume_ia": True,
    },
    "descubrir_faltantes": {
        "titulo": "Reintentar municipios sin sitio oficial",
        "comando": [sys.executable, "-u", "src/discovery/discovery_engine.py", "--faltantes"],
        "requiere_municipio": False,
        "minutos_estimados": 2,
    },
    "extraer_pendientes": {
        "titulo": "Extraer los municipios que faltan",
        "comando": [
            sys.executable, "-u", "src/extraction/extraction_engine.py", "--all", "--reanudar",
        ],
        "requiere_municipio": False,
        "minutos_estimados": 20,
        "consume_ia": True,
    },
    # Los exportes NO consumen IA: leen las bases ya construidas y las vuelcan a
    # un formato que se comparte. Se pueden correr cuantas veces haga falta.
    "exportar_excel": {
        "titulo": "Generar el Excel con todo (8 hojas)",
        "comando": [sys.executable, "-u", "src/exportar/libro_excel.py"],
        "requiere_municipio": False,
        "minutos_estimados": 1,
    },
    "exportar_fichas_pdf": {
        "titulo": "Generar las 86 fichas PDF",
        "comando": [sys.executable, "-u", "src/exportar/ficha_pdf.py", "--todos"],
        "requiere_municipio": False,
        "minutos_estimados": 2,
    },
    "exportar_ficha_pdf": {
        "titulo": "Generar la ficha PDF de este municipio",
        "comando": [sys.executable, "-u", "src/exportar/ficha_pdf.py", "--municipio"],
        "requiere_municipio": True,
        "minutos_estimados": 1,
    },
    "regenerar_html": {
        "titulo": "Regenerar el HTML autónomo",
        "comando": [sys.executable, "-u", "src/tablero/generar_html.py"],
        "requiere_municipio": False,
        "minutos_estimados": 1,
    },
}

_tareas: Dict[str, dict] = {}
_lock = threading.Lock()
_contador = 0


def listar_acciones() -> List[dict]:
    return [
        {
            "id": clave,
            "titulo": cfg["titulo"],
            "requiere_municipio": cfg["requiere_municipio"],
            "minutos_estimados": cfg["minutos_estimados"],
            "consume_ia": cfg.get("consume_ia", False),
        }
        for clave, cfg in ACCIONES.items()
    ]


def lanzar(accion: str, municipio: Optional[str] = None) -> dict:
    """Arranca la accion en segundo plano y devuelve su id."""
    global _contador
    cfg = ACCIONES.get(accion)
    if cfg is None:
        return {"error": f"Accion desconocida: {accion}"}
    if cfg["requiere_municipio"] and not municipio:
        return {"error": "Esta accion necesita un municipio"}

    comando = list(cfg["comando"])
    if cfg["requiere_municipio"]:
        comando.append(municipio)  # argumento, no interpolacion en shell

    with _lock:
        _contador += 1
        tarea_id = f"t{_contador}"
        _tareas[tarea_id] = {
            "id": tarea_id,
            "accion": accion,
            "titulo": cfg["titulo"],
            "municipio": municipio,
            "estado": "corriendo",
            "salida": [],
            "iniciada": time.strftime("%H:%M:%S"),
        }

    threading.Thread(target=_correr, args=(tarea_id, comando), daemon=True).start()
    return {"tarea_id": tarea_id}


def _correr(tarea_id: str, comando: List[str]) -> None:
    try:
        proceso = subprocess.Popen(
            comando,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,  # nunca shell: el municipio viene de afuera
        )
        for linea in proceso.stdout:  # type: ignore[union-attr]
            with _lock:
                _tareas[tarea_id]["salida"].append(linea.rstrip())
                # No dejar crecer la salida sin limite en una corrida de 86.
                if len(_tareas[tarea_id]["salida"]) > 400:
                    del _tareas[tarea_id]["salida"][:100]
        proceso.wait()
        estado = "terminada" if proceso.returncode == 0 else "fallo"
    except Exception as exc:
        with _lock:
            _tareas[tarea_id]["salida"].append(f"ERROR: {type(exc).__name__}: {exc}")
        estado = "fallo"

    with _lock:
        _tareas[tarea_id]["estado"] = estado
        _tareas[tarea_id]["fin"] = time.strftime("%H:%M:%S")


def estado(tarea_id: str) -> dict:
    with _lock:
        return dict(_tareas.get(tarea_id, {"error": "Tarea inexistente"}))


def tareas() -> List[dict]:
    with _lock:
        return [
            {k: v for k, v in t.items() if k != "salida"}
            for t in sorted(_tareas.values(), key=lambda t: t["id"], reverse=True)
        ]


__all__ = ["ACCIONES", "estado", "lanzar", "listar_acciones", "tareas"]
