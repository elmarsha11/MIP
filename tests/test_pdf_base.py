"""
Tests de pdf_base.py: lo que ficha_pdf.py y los informes agregados comparten.

Nace de sacar la creacion de FPDF de ficha_pdf.py para que informe_seguridad_pdf.py
no la duplicara. Lo que hay que probar es que el refactor no cambio el
comportamiento: mismo error legible si falta fpdf2, misma fuente con acentos si
esta, mismo fallback si no.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
_EXPORTAR = _RAIZ / "src" / "exportar"
if str(_EXPORTAR) not in sys.path:
    sys.path.insert(0, str(_EXPORTAR))

import pdf_base  # noqa: E402


class TestCrearPdf(unittest.TestCase):
    def test_devuelve_un_fpdf_con_una_pagina(self):
        pdf, _familia = pdf_base.crear_pdf("P")
        self.assertEqual(pdf.page_no(), 1)

    def test_retrato_y_apaisado_dan_paginas_distintas(self):
        retrato, _ = pdf_base.crear_pdf("P")
        apaisado, _ = pdf_base.crear_pdf("L")
        # En apaisado el ancho es mayor que el alto; en retrato, al reves.
        self.assertLess(retrato.w, retrato.h)
        self.assertGreater(apaisado.w, apaisado.h)

    def test_sin_fuente_ttf_cae_a_helvetica(self):
        original = pdf_base.FUENTE_TTF
        pdf_base.FUENTE_TTF = Path("/no/existe/arial.ttf")
        try:
            _pdf, familia = pdf_base.crear_pdf("P")
        finally:
            pdf_base.FUENTE_TTF = original
        self.assertEqual(familia, "helvetica")

    def test_con_fuente_ttf_usa_la_familia_cuerpo(self):
        candidatos = (
            ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        )
        import shutil
        import tempfile

        for regular, negrita in candidatos:
            if Path(regular).is_file() and Path(negrita).is_file():
                carpeta = Path(tempfile.mkdtemp())
                shutil.copy2(regular, carpeta / "arial.ttf")
                shutil.copy2(negrita, carpeta / "arialbd.ttf")
                original = pdf_base.FUENTE_TTF
                pdf_base.FUENTE_TTF = carpeta / "arial.ttf"
                try:
                    _pdf, familia = pdf_base.crear_pdf("P")
                finally:
                    pdf_base.FUENTE_TTF = original
                self.assertEqual(familia, "cuerpo")
                return
        self.skipTest("no hay una fuente TTF con su bold en esta maquina")

    def test_sin_fpdf2_instalado_da_un_mensaje_que_dice_que_hacer(self):
        """El caso real que motivo el mensaje: fpdf2 instalado con OTRO Python."""
        modulo_real = sys.modules.pop("fpdf", None)
        sys.modules["fpdf"] = None  # fuerza el ImportError al importar
        try:
            with self.assertRaises(SystemExit) as ctx:
                pdf_base.crear_pdf("P")
            mensaje = str(ctx.exception)
            self.assertIn("pip install -r requirements.txt", mensaje)
            self.assertIn(sys.executable, mensaje)
        finally:
            del sys.modules["fpdf"]
            if modulo_real is not None:
                sys.modules["fpdf"] = modulo_real


class TestFichaPdfSigueAndando(unittest.TestCase):
    """ficha_pdf.py se refactorizo para usar crear_pdf(): que no haya cambiado nada."""

    def test_genera_una_ficha_con_la_fuente_compartida(self):
        if str(_RAIZ / "tests") not in sys.path:
            sys.path.insert(0, str(_RAIZ / "tests"))
        import _fuente_prueba

        fuente = _fuente_prueba.resolver(pdf_base.FUENTE_TTF)
        if fuente is None:
            self.skipTest("no hay TTF con acentos en esta maquina")

        for _ruta in (_RAIZ / "src" / "tablero", _RAIZ / "src" / "discovery"):
            if str(_ruta) not in sys.path:
                sys.path.insert(0, str(_ruta))
        import consultas
        import ficha_pdf

        municipios = consultas.municipios()
        if not municipios:
            self.skipTest("sin datos de municipios en esta maquina")

        original = pdf_base.FUENTE_TTF
        pdf_base.FUENTE_TTF = fuente
        try:
            import tempfile

            destino = Path(tempfile.mkdtemp()) / "ficha.pdf"
            ruta = ficha_pdf.exportar(municipios[0]["municipio"], destino)
        finally:
            pdf_base.FUENTE_TTF = original

        self.assertIsNotNone(ruta)
        self.assertTrue(ruta.is_file())
        self.assertGreater(ruta.stat().st_size, 1000)


class TestNum(unittest.TestCase):
    def test_separador_de_miles_argentino(self):
        self.assertEqual(pdf_base._num(1234567), "1.234.567")

    def test_decimales_con_coma(self):
        self.assertEqual(pdf_base._num(1234.5, 1), "1.234,5")

    def test_none_es_un_guion(self):
        self.assertEqual(pdf_base._num(None), "—")


if __name__ == "__main__":
    unittest.main()
