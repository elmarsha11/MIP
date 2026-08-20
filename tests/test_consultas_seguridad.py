"""
Tests de consultas.seguridad(): el cruce de las dos fuentes para la pestaña.

Con base aislada, no la de los 86: lo que se prueba es el CRUCE (indice +
operativos, dos bases con universos que no siempre coinciden), no un numero
puntual de la serie real. Que el municipio B no tenga ninguna fila en
operativos tiene que dar "sin evidencia" en los 7 aspectos, no desaparecer del
listado ni romper.

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
_TABLERO = _RAIZ / "src" / "tablero"
if str(_TABLERO) not in sys.path:
    sys.path.insert(0, str(_TABLERO))

import consultas  # noqa: E402


class TestSeguridadAislado(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)

        self.sqlite_indice = base / "seguridad.sqlite"
        con = sqlite3.connect(self.sqlite_indice)
        con.execute(
            "CREATE TABLE seguridad (municipio TEXT, nivel TEXT, tasa_indice REAL, "
            "homicidios INT, tasa_homicidios REAL, robos INT, tasa_robos REAL, "
            "tasa_actividad_policial REAL, poblacion_estacional INT, fuente TEXT)"
        )
        con.executemany(
            "INSERT INTO seguridad VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                ("Municipio A", "alto", 3000.0, 2, 5.0, 100, 300.0, 10.0, 1, "SNIC"),
                ("Municipio B", "bajo", 500.0, 0, 0.0, 5, 20.0, 1.0, 0, "SNIC"),
                ("Municipio C", None, None, None, None, None, None, None, 0, "SNIC"),
            ],
        )
        con.commit()
        con.close()

        self.sqlite_operativos = base / "operativos.sqlite"
        con = sqlite3.connect(self.sqlite_operativos)
        con.execute(
            "CREATE TABLE operativos (municipio TEXT, aspecto TEXT, detalle TEXT, "
            "cita TEXT, medio TEXT, url TEXT, fecha_nota TEXT)"
        )
        con.executemany(
            "INSERT INTO operativos VALUES (?,?,?,?,?,?,?)",
            [
                ("Municipio A", "patrulla_urbana", "d", "cita 1", "El Diario",
                 "https://x.com/1", "2026-01-01"),
                ("Municipio A", "operativos", "d", "cita 2", "El Diario",
                 "https://x.com/2", "2026-01-02"),
                # Municipio B: cero filas a proposito, es el caso que importa.
            ],
        )
        con.commit()
        con.close()

        self._orig_ind, self._orig_op = consultas.SQLITE_SEGURIDAD, consultas.SQLITE_OPERATIVOS
        consultas.SQLITE_SEGURIDAD = self.sqlite_indice
        consultas.SQLITE_OPERATIVOS = self.sqlite_operativos

    def tearDown(self):
        consultas.SQLITE_SEGURIDAD, consultas.SQLITE_OPERATIVOS = self._orig_ind, self._orig_op
        self._tmp.cleanup()

    def test_trae_los_tres_municipios(self):
        d = consultas.seguridad()
        self.assertTrue(d["hay_datos"])
        self.assertEqual(d["total"], 3)
        self.assertEqual(
            {m["municipio"] for m in d["municipios"]},
            {"Municipio A", "Municipio B", "Municipio C"},
        )

    def test_nivel_nulo_se_cuenta_como_sin_dato(self):
        d = consultas.seguridad()
        c = next(m for m in d["municipios"] if m["municipio"] == "Municipio C")
        self.assertEqual(c["nivel"], "sin_dato")
        conteo = {n["nivel"]: n["n"] for n in d["niveles"]}
        self.assertEqual(conteo["sin_dato"], 1)
        self.assertEqual(conteo["alto"], 1)
        self.assertEqual(conteo["bajo"], 1)

    def test_municipio_sin_ninguna_fila_de_operativos_no_desaparece(self):
        """El caso que importa: B no tiene evidencia, pero SIGUE en la lista."""
        d = consultas.seguridad()
        b = next(m for m in d["municipios"] if m["municipio"] == "Municipio B")
        self.assertEqual(len(b["aspectos"]), 7)
        self.assertTrue(all(not a["confirmado"] for a in b["aspectos"]))

    def test_los_siete_aspectos_aparecen_siempre_confirmados_o_no(self):
        """Igual que en la ficha: si solo se listaran los confirmados, la
        ausencia se leeria como que la pregunta no se hizo."""
        d = consultas.seguridad()
        for m in d["municipios"]:
            self.assertEqual(len(m["aspectos"]), 7, m["municipio"])

    def test_aspecto_confirmado_trae_su_cita_y_url(self):
        d = consultas.seguridad()
        a = next(m for m in d["municipios"] if m["municipio"] == "Municipio A")
        patrulla = next(x for x in a["aspectos"] if x["clave"] == "patrulla_urbana")
        self.assertTrue(patrulla["confirmado"])
        self.assertEqual(patrulla["cita"], "cita 1")
        self.assertEqual(patrulla["url"], "https://x.com/1")

    def test_conteo_de_aspectos_solo_cuenta_confirmados(self):
        d = consultas.seguridad()
        conteo = {a["clave"]: a["n"] for a in d["aspectos"]}
        self.assertEqual(conteo["patrulla_urbana"], 1)
        self.assertEqual(conteo["operativos"], 1)
        self.assertEqual(conteo["allanamientos"], 0)

    def test_balneario_viaja_como_booleano(self):
        d = consultas.seguridad()
        a = next(m for m in d["municipios"] if m["municipio"] == "Municipio A")
        b = next(m for m in d["municipios"] if m["municipio"] == "Municipio B")
        self.assertIs(a["poblacion_estacional"], True)
        self.assertIs(b["poblacion_estacional"], False)

    def test_municipios_ordenados_alfabeticamente(self):
        d = consultas.seguridad()
        nombres = [m["municipio"] for m in d["municipios"]]
        self.assertEqual(nombres, sorted(nombres))


class TestSeguridadSinDatos(unittest.TestCase):
    def test_base_vacia_no_rompe(self):
        base = Path(tempfile.mkdtemp())
        vacio = base / "vacio.sqlite"
        sqlite3.connect(vacio).execute(
            "CREATE TABLE seguridad (municipio TEXT, nivel TEXT, tasa_indice REAL, "
            "homicidios INT, tasa_homicidios REAL, robos INT, tasa_robos REAL, "
            "tasa_actividad_policial REAL, poblacion_estacional INT, fuente TEXT)"
        ).connection.commit()

        orig = consultas.SQLITE_SEGURIDAD
        consultas.SQLITE_SEGURIDAD = vacio
        try:
            d = consultas.seguridad()
        finally:
            consultas.SQLITE_SEGURIDAD = orig

        self.assertFalse(d["hay_datos"])
        self.assertEqual(d["municipios"], [])


if __name__ == "__main__":
    unittest.main()
