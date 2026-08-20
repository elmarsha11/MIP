"""
Tests del contorno de los partidos.

No salen a la red: la respuesta de Overpass se simula. Lo que se prueba es lo
que puede salir mal sin que se note — que el poligono quede hecho un garabato
porque los tramos vinieron desordenados, y que la simplificacion se coma la
silueta.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
for _ruta in (_RAIZ / "src" / "territorio",):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

import limites  # noqa: E402


class TestSimplificar(unittest.TestCase):
    def test_una_recta_queda_en_dos_puntos(self):
        recta = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]
        self.assertEqual(limites.simplificar(recta, 0.01), [(0, 0), (4, 4)])

    def test_conserva_las_esquinas(self):
        cuadrado = [(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]
        self.assertEqual(len(limites.simplificar(cuadrado, 0.001)), 5)

    def test_se_come_el_ruido_sub_pixel(self):
        # Una recta con temblor de 0.0001 grados: a la escala del tablero eso es
        # menos de un pixel y no se ve.
        ruidosa = [(i / 100, (0.0001 if i % 2 else 0)) for i in range(200)]
        simple = limites.simplificar(ruidosa, limites.TOLERANCIA)
        self.assertLess(len(simple), 10)

    def test_no_se_come_una_bahia_real(self):
        # Una entrada de 0.05 grados (~5 km) tiene que sobrevivir.
        costa = [(0, 0), (1, 0), (1, -0.05), (1.05, -0.05), (1.05, 0), (2, 0)]
        simple = limites.simplificar(costa, limites.TOLERANCIA)
        self.assertIn((1, -0.05), simple)

    def test_pocos_puntos_pasan_igual(self):
        self.assertEqual(limites.simplificar([(0, 0), (1, 1)]), [(0, 0), (1, 1)])

    def test_no_desborda_con_miles_de_vertices(self):
        """Douglas-Peucker recursivo revienta la pila con un partido real."""
        import math

        circulo = [
            (math.cos(i / 5000 * 2 * math.pi), math.sin(i / 5000 * 2 * math.pi))
            for i in range(5000)
        ]
        self.assertLess(len(limites.simplificar(circulo, 0.01)), 200)


class TestEncadenado(unittest.TestCase):
    """Overpass devuelve los tramos sueltos y sin ordenar."""

    def _respuesta(self, tramos, rol="outer"):
        return {
            "elements": [{
                "members": [
                    {"role": rol,
                     "geometry": [{"lon": p[0], "lat": p[1]} for p in tramo]}
                    for tramo in tramos
                ]
            }]
        }

    def _con(self, datos):
        original = limites.consultar if hasattr(limites, "consultar") else None
        import osm

        osm.consultar = lambda q, e=False: datos
        try:
            return limites._anillos_desde_overpass(123)
        finally:
            if original:
                limites.consultar = original

    def test_cierra_un_anillo_desordenado(self):
        # El cuadrado partido en cuatro tramos, fuera de orden.
        anillos = self._con(self._respuesta([
            [(1, 1), (1, 0)],
            [(0, 0), (0, 1)],
            [(0, 1), (1, 1)],
            [(1, 0), (0, 0)],
        ]))
        self.assertEqual(len(anillos), 1)
        self.assertEqual(anillos[0][0], anillos[0][-1], "el anillo no cerro")

    def test_da_vuelta_el_tramo_si_hace_falta(self):
        anillos = self._con(self._respuesta([
            [(0, 0), (0, 1)],
            [(1, 1), (0, 1)],   # invertido respecto del anterior
            [(1, 1), (1, 0), (0, 0)],
        ]))
        self.assertEqual(len(anillos), 1)
        self.assertEqual(anillos[0][0], anillos[0][-1])

    def test_ignora_los_anillos_interiores(self):
        datos = self._respuesta([[(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]], rol="inner")
        self.assertEqual(self._con(datos), [])

    def test_sin_respuesta_devuelve_vacio(self):
        self.assertEqual(self._con(None), [])

    def test_tramo_de_un_punto_se_descarta(self):
        self.assertEqual(self._con(self._respuesta([[(0, 0)]])), [])


class TestBajar(unittest.TestCase):
    def test_calcula_el_recuadro_y_la_reduccion(self):
        import osm

        cuadrado = [(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]
        osm.consultar = lambda q, e=False: {
            "elements": [{"members": [
                {"role": "outer",
                 "geometry": [{"lon": p[0], "lat": p[1]} for p in cuadrado]}
            ]}]
        }
        lim = limites.bajar("Prueba", 1)
        self.assertEqual((lim["lon_min"], lim["lon_max"]), (0, 1))
        self.assertEqual((lim["lat_min"], lim["lat_max"]), (0, 1))
        self.assertEqual(lim["puntos_crudos"], 5)

    def test_sin_geometria_devuelve_none(self):
        import osm

        osm.consultar = lambda q, e=False: {"elements": []}
        self.assertIsNone(limites.bajar("Prueba", 1))


if __name__ == "__main__":
    unittest.main()
