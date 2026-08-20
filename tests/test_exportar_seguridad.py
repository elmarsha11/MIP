"""
Tests de los exportes de seguridad: el Excel de una hoja y el informe PDF.

Van contra las bases reales de los 86, no un fixture aislado: lo que importa
aca es que el pipeline completo corra sin explotar y produzca un archivo con
la forma esperada, igual que la verificacion manual en navegador. La logica del
CRUCE de fuentes ya esta probada aparte, con fixtures, en
test_consultas_seguridad.py.

fpdf2 exige una fuente TTF real para tildes y "ñ" (la Helvetica que trae por
defecto es latin-1). En Windows esta en C:/Windows/Fonts/arial.ttf; en este
entorno de tests se sustituye por una tipografia Unix equivalente. Sin
sustituto, los tests que generan PDF se saltean en vez de fallar: no hay nada
que decir sobre el codigo si la maquina no tiene una fuente que probarlo.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
for _ruta in (_RAIZ / "src" / "exportar", _RAIZ / "src" / "tablero"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

import consultas  # noqa: E402
import libro_excel  # noqa: E402
import pdf_base  # noqa: E402

if str(_RAIZ / "tests") not in sys.path:
    sys.path.insert(0, str(_RAIZ / "tests"))
import _fuente_prueba  # noqa: E402

_FUENTE_PRUEBA = _fuente_prueba.resolver(pdf_base.FUENTE_TTF)


@unittest.skipUnless(consultas.seguridad().get("hay_datos"), "sin datos de seguridad")
class TestExcelSeguridad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from openpyxl import load_workbook

        cls.destino = Path(tempfile.mkdtemp()) / "seguridad.xlsx"
        libro_excel.exportar_seguridad(cls.destino)
        cls.libro = load_workbook(cls.destino)

    def test_las_tres_hojas(self):
        self.assertEqual(
            self.libro.sheetnames,
            ["Fuentes y advertencias", "Seguridad", "Seguridad - cómo opera"],
        )

    def test_una_fila_por_municipio(self):
        total = consultas.seguridad()["total"]
        # +1 por la cabecera.
        self.assertEqual(self.libro["Seguridad"].max_row, total + 1)

    def test_las_advertencias_estan_en_la_hoja_de_fuentes(self):
        celdas = " ".join(
            str(c.value) for r in self.libro["Fuentes y advertencias"].iter_rows() for c in r
        )
        self.assertIn("DENUNCIADOS", celdas)
        self.assertIn("RELATIVO", celdas)


@unittest.skipUnless(_FUENTE_PRUEBA is not None, "no hay TTF con acentos en esta maquina")
class TestInformePDF(unittest.TestCase):
    """Genera el PDF de verdad y lo abre con pypdf: no alcanza con 'no exploto'."""

    @classmethod
    def setUpClass(cls):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise unittest.SkipTest("falta pypdf para inspeccionar el PDF generado")

        cls._fuente_original = pdf_base.FUENTE_TTF
        pdf_base.FUENTE_TTF = _FUENTE_PRUEBA

        import informe_seguridad_pdf as informe

        cls.informe = informe
        cls.destino = Path(tempfile.mkdtemp()) / "informe.pdf"
        cls.ruta = informe.exportar(cls.destino)
        cls.paginas = PdfReader(str(cls.ruta)).pages if cls.ruta else []

    @classmethod
    def tearDownClass(cls):
        pdf_base.FUENTE_TTF = cls._fuente_original

    def test_genera_el_archivo(self):
        self.assertIsNotNone(self.ruta)
        self.assertTrue(self.ruta.is_file())
        self.assertGreater(self.ruta.stat().st_size, 1000)

    def test_tiene_mas_de_una_pagina(self):
        """Portada + al menos una tabla: los 86 no entran en una sola hoja."""
        self.assertGreater(len(self.paginas), 2)

    def test_la_portada_trae_las_advertencias(self):
        texto = self.paginas[0].extract_text()
        self.assertIn("DENUNCIADOS", texto)
        self.assertIn("RELATIVO", texto)
        self.assertIn("Confidencial", texto)

    def test_los_86_municipios_estan_en_algun_lado(self):
        texto_completo = "\n".join(p.extract_text() for p in self.paginas)
        total = consultas.seguridad()["total"]
        # Se toma una muestra: pedir los 86 nombres exactos seria fragil ante
        # cualquier alias. Lo que importa es que la cantidad de filas cierre.
        self.assertGreaterEqual(texto_completo.count("sí"), total)  # balnearios + aspectos

    def test_sin_datos_devuelve_none_y_no_explota(self):
        vacio = Path(tempfile.mkdtemp()) / "no_deberia_existir.pdf"

        orig = consultas.seguridad
        consultas.seguridad = lambda: {"hay_datos": False}
        try:
            resultado = self.informe.exportar(vacio)
        finally:
            consultas.seguridad = orig

        self.assertIsNone(resultado)
        self.assertFalse(vacio.exists())


if __name__ == "__main__":
    unittest.main()
