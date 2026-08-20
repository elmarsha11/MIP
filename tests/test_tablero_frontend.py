"""
Tests del frontend del tablero, sin navegador.

Existen por un error concreto: se agrego `ambiental: verAmbiental` al mapa de
vistas y el bloque que DEFINE `verAmbiental` no llego al archivo. El literal del
mapa se evalua en cada click, asi que referenciar una funcion inexistente lanza
ReferenceError y **se cae el tablero entero**, no solo la pestaña nueva.

`node --check` no lo agarra: es un chequeo de sintaxis y el archivo era
sintacticamente valido. Un identificador sin definir solo explota al ejecutarse.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "tablero" / "web"
APP_JS = WEB / "app.js"
INDEX = WEB / "index.html"


class TestMapaDeVistas(unittest.TestCase):
    """Cada vista tiene boton, seccion y funcion. Las tres cosas o ninguna."""

    @classmethod
    def setUpClass(cls):
        cls.js = APP_JS.read_text(encoding="utf-8")
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.botones = re.findall(r'data-vista="([a-z-]+)"', cls.html)
        bloque = re.search(r"function cargarVista\(vista\)\s*\{(.*?)\}\[vista\]", cls.js, re.S)
        assert bloque, "no se encontro el mapa de vistas en cargarVista"
        cls.mapa = dict(re.findall(r"(\w+):\s*(\w+)", bloque.group(1)))

    def test_toda_funcion_del_mapa_existe(self):
        """El error que motivo este archivo."""
        for vista, funcion in self.mapa.items():
            self.assertRegex(
                self.js,
                rf"(async\s+)?function\s+{re.escape(funcion)}\s*\(",
                f"el mapa de vistas apunta a {funcion}() para '{vista}' y no está definida. "
                "Eso lanza ReferenceError y tumba TODO el tablero, no solo esa pestaña.",
            )

    def test_todo_boton_tiene_seccion_en_el_html(self):
        for vista in self.botones:
            self.assertIn(
                f'id="vista-{vista}"', self.html,
                f'el botón "{vista}" no tiene su <section id="vista-{vista}">',
            )

    def test_todo_boton_tiene_entrada_en_el_mapa(self):
        for vista in self.botones:
            self.assertIn(
                vista, self.mapa,
                f'el botón "{vista}" no está en cargarVista: la pestaña se abre vacía',
            )

    def test_ambiental_esta_completa(self):
        """La pestaña de este cambio, explicitamente."""
        self.assertIn("ambiental", self.botones)
        self.assertIn("ambiental", self.mapa)
        self.assertRegex(self.js, r"async function verAmbiental\s*\(")
        for elemento in ("ambiental-categoria", "ambiental-estado",
                         "ambiental-cuenta", "ambiental-resumen", "ambiental-contenido"):
            self.assertIn(f'id="{elemento}"', self.html, elemento)

    def test_seguridad_esta_completa(self):
        """La pestaña de este cambio, explicitamente."""
        self.assertIn("seguridad", self.botones)
        self.assertIn("seguridad", self.mapa)
        self.assertRegex(self.js, r"async function verSeguridad\s*\(")
        for elemento in ("seguridad-nivel", "seguridad-aspecto", "seguridad-cuenta",
                         "seguridad-resumen", "seguridad-contenido",
                         "seguridad-excel", "seguridad-pdf"):
            self.assertIn(f'id="{elemento}"', self.html, elemento)

    def test_seguridad_pdf_se_deshabilita_en_estatico_no_se_esconde(self):
        """Un boton que no funciona sin servidor tiene que explicarse, no desaparecer.

        Es la misma leccion que costo el boton de Excel de ambiental: esconder
        un boton en el export deja al que lo abre sin ninguna pista de que
        faltaba o por que.
        """
        self.assertIn('$("#seguridad-pdf")', self.js)
        self.assertIn("requiere servidor", self.js.lower())
        self.assertNotIn(
            'if (botonPdf) botonPdf.style.display', self.js,
            "el boton de PDF no deberia esconderse en modo estatico",
        )


class TestModoEstatico(unittest.TestCase):
    """El HTML generado no tiene servidor: los datos viajan incrustados.

    Si una vista pide una ruta que `leerIncrustado` no conoce, en el navegador
    anda y en el archivo exportado aparece vacía. Es una divergencia que solo se
    ve abriendo el export, o sea tarde.
    """

    @classmethod
    def setUpClass(cls):
        cls.js = APP_JS.read_text(encoding="utf-8")
        bloque = re.search(r"function leerIncrustado\(ruta\)\s*\{(.*?)\n\}", cls.js, re.S)
        assert bloque, "no se encontro leerIncrustado"
        cls.incrustado = bloque.group(1)

    def test_toda_ruta_pedida_por_api_esta_en_el_shim(self):
        rutas = {r for r in re.findall(r'api\("([a-z-]+)"\)', self.js)}
        for ruta in rutas:
            self.assertIn(
                f"{ruta}:" if ruta.isidentifier() else f'"{ruta}"',
                self.incrustado,
                f'api("{ruta}") no está en leerIncrustado: esa vista queda vacía '
                "en el HTML exportado, aunque funcione con el servidor.",
            )

    def test_ambiental_viaja_en_el_export(self):
        self.assertIn("ambiental: D.ambiental", self.incrustado)


if __name__ == "__main__":
    unittest.main()
