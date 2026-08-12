"""
Tests del motor de seguridad.

Lo que se prueba no es que sume bien: es que **no pueda producir un ranking que
mienta**. Cada test fija una decision metodologica que, si se revierte, cambia
quien queda arriba en una lista que va a decidir a que municipio se visita.
"""

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
for _ruta in (_RAIZ / "src" / "seguridad", _RAIZ / "src" / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from indice import (  # noqa: E402
    ACTIVIDAD_POLICIAL,
    DELITOS_DEL_INDICE,
    EXCLUIDOS,
    POBLACION_ESTACIONAL,
    clasificar,
    cortes_por_terciles,
)
from snic import ALIAS_SNIC, Hecho, sin_datos_en, ultimo_anio  # noqa: E402


class TestQueEntraAlIndice(unittest.TestCase):
    def test_los_suicidios_no_entran_a_ningun_grupo(self):
        """Un suicidio no es un delito contra un tercero. Contarlo como
        inseguridad es un error de categoria."""
        for delito in EXCLUIDOS:
            with self.subTest(delito=delito):
                self.assertNotIn(delito, DELITOS_DEL_INDICE)
                self.assertNotIn(delito, ACTIVIDAD_POLICIAL)

    def test_estupefacientes_y_armas_quedan_fuera_del_indice(self):
        """Miden despliegue policial, no victimizacion.

        En Chascomus 2025 el delito mas frecuente es "Tenencia simple atenuada
        para uso personal": 693 hechos. Sumarlo haria que un partido con policia
        activa en drogas figure como mas inseguro que uno donde la policia no
        sale.
        """
        for delito in ACTIVIDAD_POLICIAL:
            with self.subTest(delito=delito):
                self.assertNotIn(delito, DELITOS_DEL_INDICE)
        self.assertTrue(any("estupefacientes" in d for d in ACTIVIDAD_POLICIAL))
        self.assertTrue(any("armas" in d for d in ACTIVIDAD_POLICIAL))

    def test_el_indice_tiene_las_tres_familias_con_victima(self):
        self.assertIn("Homicidios dolosos", DELITOS_DEL_INDICE)
        self.assertIn("Hurtos", DELITOS_DEL_INDICE)
        self.assertIn("Abuso sexual simple", DELITOS_DEL_INDICE)

    def test_no_hay_delitos_repetidos(self):
        """Un delito en dos grupos se contaria dos veces en la tasa."""
        self.assertEqual(len(DELITOS_DEL_INDICE), len(set(DELITOS_DEL_INDICE)))


class TestClasificacion(unittest.TestCase):
    def test_los_terciles_parten_en_tres_grupos_parejos(self):
        tasas = list(range(1, 91))
        cortes = cortes_por_terciles(tasas)
        niveles = [clasificar(t, cortes) for t in tasas]
        for nivel in ("bajo", "medio", "alto"):
            with self.subTest(nivel=nivel):
                self.assertGreater(niveles.count(nivel), 20)

    def test_el_nivel_es_relativo_al_conjunto(self):
        """La misma tasa puede ser 'alto' en un conjunto y 'bajo' en otro.

        Es la propiedad que obliga a rotular el nivel como relativo: no dice
        'peligroso', dice 'en el tercio superior de estos 86'.
        """
        self.assertEqual(clasificar(100, cortes_por_terciles([1, 2, 3])), "alto")
        self.assertEqual(clasificar(100, cortes_por_terciles([500, 900, 1500])), "bajo")


class TestPoblacionEstacional(unittest.TestCase):
    def test_los_balnearios_del_top_estan_marcados(self):
        """Sin la marca, el ranking le dice al lector que la costa es peligrosa.

        Medido sobre 2025: 6 de los 10 primeros son balnearios, siendo apenas 14
        de los 86. La tasa divide por poblacion residente y los hechos ocurren
        sobre la de verano.
        """
        for municipio in ("Villa Gesell", "Pinamar", "Monte Hermoso", "General Alvarado"):
            with self.subTest(municipio=municipio):
                self.assertIn(municipio, POBLACION_ESTACIONAL)

    def test_un_partido_mediterraneo_no_esta_marcado(self):
        for municipio in ("Chascomús", "Navarro", "Chivilcoy", "Bragado"):
            with self.subTest(municipio=municipio):
                self.assertNotIn(municipio, POBLACION_ESTACIONAL)


class TestAlias(unittest.TestCase):
    def test_coronel_rosales_tiene_los_dos_nombres_del_snic(self):
        """El SNIC se renombra a si mismo a mitad de la serie.

        "Coronel de Marina L. Rosales" hasta 2016 y "...Leonardo Rosales" desde
        2017. Con un solo alias el partido perdia nueve anios.
        """
        nombres = ALIAS_SNIC["Coronel Rosales"]
        self.assertIn("Coronel de Marina Leonardo Rosales", nombres)
        self.assertIn("Coronel de Marina L. Rosales", nombres)

    def test_todos_los_alias_son_tuplas(self):
        """Si alguno queda como string, iterar sus letras generaria equivalencias
        de una sola letra y un municipio podria quedarse con el delito de otro."""
        for municipio, nombres in ALIAS_SNIC.items():
            with self.subTest(municipio=municipio):
                self.assertIsInstance(nombres, tuple)


class TestAnioDeReferencia(unittest.TestCase):
    def _datos(self, anios_por_municipio):
        return {
            m: [Hecho(m, a, "Hurtos", 1, 1.0) for a in anios]
            for m, anios in anios_por_municipio.items()
        }

    def test_un_hueco_solitario_no_arrastra_a_todos_al_pasado(self):
        """El bug de la primera version.

        Se pedia el anio comun a TODOS y devolvia 2016 —diez anios viejo— porque
        un unico partido tenia un hueco. Sacrificar la actualidad de 85 por uno
        es peor que declarar que a ese uno le falta el dato.
        """
        datos = self._datos(
            {f"M{i}": range(2014, 2026) for i in range(20)} | {"Rezagado": range(2014, 2017)}
        )
        self.assertEqual(ultimo_anio(datos), 2025)
        self.assertEqual(sin_datos_en(datos, 2025), ["Rezagado"])

    def test_todos_comparten_el_mismo_anio(self):
        """Comparar 2025 de uno contra 2019 de otro seria un ranking falso."""
        datos = self._datos({f"M{i}": range(2014, 2026) for i in range(5)})
        self.assertEqual(ultimo_anio(datos), 2025)
        self.assertEqual(sin_datos_en(datos, 2025), [])

    def test_sin_datos_devuelve_none(self):
        self.assertIsNone(ultimo_anio({}))


if __name__ == "__main__":
    unittest.main()
