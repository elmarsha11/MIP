"""
Tests del importador del relevamiento ambiental.

Lo que se prueba de verdad es la reparacion del CSV. El archivo trae los campos
con comas SIN comillas, asi que una lista como "industrias lactea, quesera,
agroindustrial" se partio en varios campos y corrio todo lo de la derecha: en
Suipacha eso dejaba los Puntos Verdes bajo el titulo "Fuentes Oficiales", que en
realidad era la columna de GIRSU desplazada.

Importar eso sin reparar seria meter datos corridos en la base, que es
exactamente lo que MIP existe para evitar.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
for _ruta in (_RAIZ / "src" / "temas", _RAIZ / "src" / "extraction"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

import plan_ambiental as pa  # noqa: E402


class TestReparacion(unittest.TestCase):
    def test_campo_abierto_se_pega_con_el_siguiente(self):
        """El caso Suipacha: una lista de industrias partida por sus comas."""
        campos = [
            "Fiscalizacion a cargo de la Provincia. Cuenta con SIP con industrias lactea",
            "quesera",
            "agroindustrial y metalmecanica liviana.",
        ]
        self.assertEqual(
            pa.reparar_campos(campos),
            ["Fiscalizacion a cargo de la Provincia. Cuenta con SIP con industrias "
             "lactea, quesera, agroindustrial y metalmecanica liviana."],
        )

    def test_minuscula_delata_continuacion_aunque_el_anterior_cierre(self):
        """El caso Ayacucho: "(Mateo Hermanos S.A.)" parece cierre y no lo es."""
        campos = [
            "Planta de fundicion de plomo (Mateo Hermanos S.A.)",
            "monitoreada estrictamente por provincia y municipio.",
        ]
        self.assertEqual(len(pa.reparar_campos(campos)), 1)

    def test_campos_completos_no_se_pegan(self):
        campos = ["Primera frase completa.", "Segunda frase completa."]
        self.assertEqual(len(pa.reparar_campos(campos)), 2)

    def test_una_url_nunca_es_continuacion(self):
        """Las URLs empiezan en minuscula pero no continuan nada."""
        campos = ["Texto que cierra bien.", "https://municipio.gob.ar/ambiente"]
        self.assertEqual(len(pa.reparar_campos(campos)), 2)

    def test_url_despues_de_campo_abierto_igual_se_separa(self):
        campos = ["Lista de cosas sin cerrar", "https://x.gob.ar"]
        self.assertEqual(len(pa.reparar_campos(campos)), 2)

    def test_ignora_campos_vacios(self):
        self.assertEqual(pa.reparar_campos(["", "  ", "Uno solo."]), ["Uno solo."])

    def test_sin_campos(self):
        self.assertEqual(pa.reparar_campos([]), [])


class TestInvariantes(unittest.TestCase):
    """El importador se planta antes de guardar datos corridos."""

    def _csv(self, filas):
        tmp = Path(tempfile.mkdtemp()) / "p.csv"
        cab = "ID,Municipio,Seccion,Poblacion,A,B,C,D,E,F\n"
        tmp.write_text(cab + "\n".join(filas), encoding="utf-8")
        return tmp

    def test_fila_que_no_reconstruye_a_seis_falla(self):
        # Solo tres campos de contenido: falta la mitad.
        ruta = self._csv(["MUN-1,Prueba,Primera,1000,Uno.,Dos.,https://x.gob.ar"])
        with self.assertRaises(pa.FilaMalformada) as ctx:
            pa.leer(ruta)
        self.assertIn("Prueba", str(ctx.exception))

    def test_ultima_columna_sin_url_falla(self):
        ruta = self._csv(
            ["MUN-1,Prueba,Primera,1000,Uno.,Dos.,Tres.,Cuatro.,Cinco.,Sin fuente."]
        )
        with self.assertRaises(pa.FilaMalformada) as ctx:
            pa.leer(ruta)
        self.assertIn("corridas", str(ctx.exception))

    def test_fila_bien_formada_pasa(self):
        ruta = self._csv(
            ["MUN-1,Prueba,Primera,1000,Uno.,Dos.,Tres.,Cuatro.,Cinco.,https://x.gob.ar"]
        )
        filas = pa.leer(ruta)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0].textos["promotores_ambientales"], "Uno.")
        self.assertEqual(filas[0].fuentes, "https://x.gob.ar")


class TestAlias(unittest.TestCase):
    """Cinco municipios se escriben distinto que en el resto del sistema."""

    def test_los_cinco_se_traducen(self):
        self.assertEqual(pa.ALIAS["leandro n. alem"], "Alem")
        self.assertEqual(pa.ALIAS["maipú"], "Maipu")
        self.assertEqual(pa.ALIAS["saavedra (pigüé)"], "Saavedra")
        self.assertEqual(pa.ALIAS["tapalqué"], "Tapalque")
        self.assertEqual(pa.ALIAS["gonzales chaves"], "Gonzales Cháves")


class TestEstadoDerivado(unittest.TestCase):
    def test_competencia_mixta(self):
        t = ("Competencia del Ministerio de Ambiente de la PBA. El municipio "
             "realiza inspecciones conjuntas.")
        self.assertEqual(pa.competencia_fiscalizacion(t), "mixta")

    def test_competencia_solo_provincial(self):
        t = "Fiscalizacion a cargo exclusivo del Ministerio de Ambiente de la PBA."
        self.assertEqual(pa.competencia_fiscalizacion(t), "provincial")

    def test_competencia_solo_municipal(self):
        t = "El municipio inspecciona los establecimientos del partido."
        self.assertEqual(pa.competencia_fiscalizacion(t), "municipal")

    def test_girsu_reconoce_planta_y_puntos(self):
        t = "Planta de tratamiento de RSU y red de puntos verdes en barrios."
        self.assertEqual(
            pa.estado_derivado("girsu_residuos", t), "planta_propia+puntos_verdes"
        )

    def test_sin_senal_se_dice(self):
        self.assertEqual(
            pa.estado_derivado("girsu_residuos", "Texto sin nada reconocible."),
            "sin_senal",
        )

    def test_tolera_tildes(self):
        t = "Reserva Natural Municipal y plan de arbolado público."
        self.assertEqual(
            pa.estado_derivado("areas_arbolado", t), "reserva_declarada+plan_arbolado"
        )


class TestCSVReal(unittest.TestCase):
    """Contra el archivo de verdad: 86 filas, todas reconstruyen."""

    @classmethod
    def setUpClass(cls):
        if not pa.CSV_CRUDO.exists():
            raise unittest.SkipTest(f"falta {pa.CSV_CRUDO}")
        cls.filas = pa.leer()

    def test_los_86(self):
        self.assertEqual(len(self.filas), 86)

    def test_todos_tienen_las_cinco_categorias(self):
        for f in self.filas:
            self.assertEqual(len(f.textos), 5, f.municipio)
            for cat, texto in f.textos.items():
                self.assertTrue(texto.strip(), f"{f.municipio}/{cat} vacio")

    def test_todos_tienen_fuente_con_url(self):
        for f in self.filas:
            self.assertRegex(f.fuentes, r"https?://|www\.", f.municipio)

    def test_suipacha_quedo_bien_alineado(self):
        """La fila que delato el bug: los Puntos Verdes son GIRSU, no la fuente."""
        s = next(f for f in self.filas if f.municipio == "Suipacha")
        self.assertIn("Puntos Verdes", s.textos["girsu_residuos"])
        self.assertIn("3ra categoría", s.textos["fiscalizacion_3ra"])
        self.assertIn("quesera", s.textos["fiscalizacion_3ra"])
        self.assertNotIn("Puntos Verdes", s.fuentes)

    def test_ayacucho_quedo_bien_alineado(self):
        a = next(f for f in self.filas if f.municipio == "Ayacucho")
        self.assertIn("Mateo Hermanos", a.textos["fiscalizacion_3ra"])
        self.assertIn("monitoreada", a.textos["fiscalizacion_3ra"])

    def test_importar_y_leer_de_la_base(self):
        base = Path(tempfile.mkdtemp()) / "t.sqlite"
        self.assertEqual(pa.importar(pa.CSV_CRUDO, base), 86)
        con = sqlite3.connect(base)
        try:
            n = con.execute("SELECT COUNT(*) FROM plan_ambiental").fetchone()[0]
            municipios = con.execute(
                "SELECT COUNT(DISTINCT municipio) FROM plan_ambiental"
            ).fetchone()[0]
            sin_estado = con.execute(
                "SELECT COUNT(*) FROM plan_ambiental WHERE estado IS NULL OR estado = ''"
            ).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(municipios, 86)
        self.assertEqual(n, 86 * 5)
        self.assertEqual(sin_estado, 0)


if __name__ == "__main__":
    unittest.main()
