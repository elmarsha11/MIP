"""
Sustituto de arial.ttf para los tests que generan PDF fuera de Windows.

fpdf2 necesita una fuente TTF real para tildes y "ñ": la Helvetica que trae por
defecto es latin-1. En Windows esta en C:/Windows/Fonts/arial.ttf; en Linux/CI se
sustituye por una tipografia equivalente con su par Regular+Bold, copiada con los
nombres que pdf_base.py espera (arial.ttf / arialbd.ttf).

No es codigo de produccion: solo lo importan los tests.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

_CANDIDATOS = (
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)


def resolver(fuente_ttf_actual: Path) -> Optional[Path]:
    """La fuente ya configurada si existe, o un sustituto Unix copiado con
    los nombres esperados. None si no hay ninguna de las dos cosas."""
    if fuente_ttf_actual.exists():
        return fuente_ttf_actual
    for regular, negrita in _CANDIDATOS:
        if Path(regular).is_file() and Path(negrita).is_file():
            carpeta = Path(tempfile.mkdtemp())
            destino = carpeta / "arial.ttf"
            shutil.copy2(regular, destino)
            shutil.copy2(negrita, carpeta / "arialbd.ttf")
            return destino
    return None
