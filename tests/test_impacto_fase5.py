"""
Tests Fase 5 - Modelo de impacto.

Lo que se prueba es que el modelo NO pueda producir un numero sin procedencia.
Es el reemplazo de la constante de $31.001, que tenia R^2 = 1,0 y ninguna fuente.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "impacto"))
sys.path.insert(1, str(PROJECT_ROOT / "src" / "discovery"))

from pydantic import ValidationError  # noqa: E402

from modelo_turnos import advertencias, calcular, sensibilidad, techo_de_precio_anual  # noqa: E402
from parametros import (  # noqa: E402
    VALOR_HORA_VECINO,
    Parametro,
    TipoParametro,
    parametros_sin_fuente,
)


class TestProcedenciaObligatoria(unittest.TestCase):
    """Ningun numero entra al modelo sin decir de donde sale."""

    def test_un_parametro_oficial_sin_fuente_no_se_puede_construir(self):
        with self.assertRaises(ValidationError) as ctx:
            Parametro(
                nombre="constante_magica", valor=31001.0, unidad="ARS/hab",
                tipo=TipoParametro.OFICIAL,
            )
        self.assertIn("procedencia", str(ctx.exception).lower())

    def test_un_supuesto_sin_rango_no_se_puede_construir(self):
        """Un supuesto sin rango se lee como si fuera un dato."""
        with self.assertRaises(ValidationError):
            Parametro(
                nombre="x", valor=2.0, unidad="u", tipo=TipoParametro.SUPUESTO
            )

    def test_el_valor_hora_tiene_norma_citable(self):
        self.assertIs(VALOR_HORA_VECINO.tipo, TipoParametro.OFICIAL)
        self.assertTrue(VALOR_HORA_VECINO.es_afirmable)
        self.assertIn("Resolucion 9/2025", VALOR_HORA_VECINO.fuente)
        self.assertIn("SMVM", VALOR_HORA_VECINO.citar() + VALOR_HORA_VECINO.fuente)

    def test_los_supuestos_no_son_afirmables(self):
        for p in parametros_sin_fuente():
            with self.subTest(parametro=p.nombre):
                self.assertFalse(p.es_afirmable)
                self.assertIn("SUPUESTO", p.citar())

    def test_hay_supuestos_pendientes_y_se_declaran(self):
        """Si algun dia esta lista queda vacia, el modelo pasa a ser afirmable."""
        self.assertGreater(len(parametros_sin_fuente()), 0)


class TestCalculo(unittest.TestCase):
    def _costo(self, poblacion=20000):
        return calcular(
            "Pinamar", "MUN-BA-001", poblacion, "presencial",
            "Para obtener el turno acercarse a la mesa de admision",
            "https://pinamar.gob.ar/salud/",
        )

    def test_devuelve_rango_no_un_numero_unico(self):
        c = self._costo()
        self.assertLess(c.costo_min, c.costo_central)
        self.assertLess(c.costo_central, c.costo_max)

    def test_siempre_se_rotula_como_estimacion(self):
        self.assertTrue(self._costo().es_estimacion)

    def test_escala_con_la_poblacion(self):
        chico, grande = self._costo(10000), self._costo(20000)
        self.assertAlmostEqual(grande.costo_central / chico.costo_central, 2.0, places=6)

    def test_conserva_la_evidencia_de_la_ausencia(self):
        c = self._costo()
        self.assertIn("mesa de admision", c.evidencia)
        self.assertTrue(c.url)

    def test_las_advertencias_nombran_las_dos_trampas(self):
        texto = " ".join(advertencias()).lower()
        self.assertIn("estimacion", texto)
        self.assertIn("no ahorro del presupuesto", texto)
        self.assertIn("piso", texto)

    def test_el_techo_de_precio_es_una_fraccion_del_valor(self):
        c = self._costo()
        t_min, t_cen, t_max = techo_de_precio_anual(c, fraccion_del_valor=0.10)
        self.assertAlmostEqual(t_cen, c.costo_central * 0.10, places=6)
        self.assertLess(t_min, t_max)


class TestSensibilidad(unittest.TestCase):
    """Convierte 'no sabemos' en un plan de medicion."""

    def test_ordena_por_cuanto_ensancha_el_resultado(self):
        filas = sensibilidad()
        self.assertTrue(filas)
        factores = [f[1] for f in filas]
        self.assertEqual(factores, sorted(factores, reverse=True))

    def test_cada_supuesto_dice_como_cerrarlo(self):
        for nombre, _, como in sensibilidad():
            with self.subTest(parametro=nombre):
                self.assertGreater(len(como), 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
