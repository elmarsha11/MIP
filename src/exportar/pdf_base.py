"""
Lo que comparten todos los PDF de MIP: crear el documento sin romper feo.

Vive aparte porque `ficha_pdf.py` (un municipio, retrato) y los informes
agregados (los 86 juntos, apaisado) necesitan layouts distintos, pero los dos
tropiezan con el mismo par de problemas si se escriben cada uno por su lado:
fpdf2 puede no estar instalado con el interprete que corre el servidor, y la
Helvetica que trae fpdf es latin-1 y rompe con "Chascomús".
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

FUENTE_TTF = Path("C:/Windows/Fonts/arial.ttf")

NEGRO = (34, 34, 34)
GRIS = (110, 110, 110)
ROJO = (170, 0, 0)
LINEA = (200, 200, 200)


def _num(x, dec: int = 0) -> str:
    if x is None:
        return "—"
    s = f"{x:,.{dec}f}"
    entero, _, d = s.partition(".")
    return f"{entero.replace(',', '.')},{d}" if d else entero.replace(",", ".")


def crear_pdf(orientacion: str = "P"):
    """Un FPDF con pagina propia y fuente con acentos, o un error legible.

    Un ImportError crudo no le dice a nadie que hacer, y desde el tablero
    aparece como "fallo" a secas. El caso real: se instalo fpdf2 con un Python
    y el servidor se levanto con otro, asi que anda desde la terminal y falla
    desde el boton.
    """
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise SystemExit(
            "Falta fpdf2, que genera los PDF.\n"
            f"  Instalalo con ESTE interprete:\n"
            f"    {sys.executable} -m pip install -r requirements.txt\n"
            "  Si desde la terminal anda y desde el tablero no, es que el\n"
            "  servidor se levanto con otro Python: las acciones usan el\n"
            "  interprete que corre el servidor."
        ) from exc

    pdf = FPDF(orientation=orientacion, format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)
    if FUENTE_TTF.exists():
        pdf.add_font("cuerpo", "", str(FUENTE_TTF))
        pdf.add_font("cuerpo", "B", str(FUENTE_TTF.with_name("arialbd.ttf")))
        familia = "cuerpo"
    else:
        familia = "helvetica"
    pdf.add_page()
    return pdf, familia


__all__ = ["FUENTE_TTF", "GRIS", "LINEA", "NEGRO", "ROJO", "_num", "crear_pdf"]
