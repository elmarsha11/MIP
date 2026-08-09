"""
Tests Fase 6 - Censo territorial.

Sin red: se prueban la clasificacion de etiquetas OSM y las reglas del modelo.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "territorio"))
sys.path.insert(1, str(PROJECT_ROOT / "src" / "discovery"))

from pydantic import ValidationError  # noqa: E402

from entidades import (  # noqa: E402
    CAPAS,
    REQUIEREN_NOMBRE,
    CensoMunicipio,
    Entidad,
    FuenteEntidad,
    TipoEntidad,
)
from osm import clasificar  # noqa: E402

FECHA = "2026-08-09T12:00:00Z"


def entidad(**kw) -> Entidad:
    datos = dict(
        municipio="Chascomús", id_municipio="MUN-BA-001",
        tipo=TipoEntidad.HOSPITAL, nombre="Hospital Municipal San Vicente de Paul",
        latitud=-35.5763099, longitud=-58.0077421,
        fuente=FuenteEntidad.OSM, id_en_fuente="node/123456", fecha=FECHA,
    )
    datos.update(kw)
    return Entidad(**datos)


class TestClasificacion(unittest.TestCase):
    """OSM etiqueta grueso; MIP necesita fino. El nombre desempata."""

    def test_farmacia_no_es_un_centro_de_salud(self):
        """El bug real: amenity=pharmacy trae healthcare=pharmacy, caia en la
        heuristica de salud y 13 farmacias de Chascomus entraron como CAPS."""
        for etiquetas in (
            {"amenity": "pharmacy", "healthcare": "pharmacy", "name": "Bellingeri"},
            {"amenity": "pharmacy", "name": "Aprile"},
            {"healthcare": "pharmacy"},
        ):
            with self.subTest(etiquetas=etiquetas):
                self.assertIs(clasificar(etiquetas), TipoEntidad.FARMACIA)

    def test_el_nombre_distingue_hospital_de_caps(self):
        """OSM marca los dos como amenity=hospital y esa diferencia es el dato."""
        self.assertIs(
            clasificar({"amenity": "hospital", "name": "Hospital Municipal San Vicente de Paul"}),
            TipoEntidad.HOSPITAL,
        )
        self.assertIs(
            clasificar({"amenity": "hospital", "name": "CAPS El Porteño"}), TipoEntidad.CAPS
        )
        self.assertIs(
            clasificar({"amenity": "hospital", "name": "Centro de Atencion Primaria de Salud"}),
            TipoEntidad.CAPS,
        )

    def test_el_nombre_distingue_niveles_educativos(self):
        casos = {
            "Jardín De Infantes 906": TipoEntidad.JARDIN,
            "Escuela Primaria 3 Sargento Cabral": TipoEntidad.ESCUELA_PRIMARIA,
            "Escuela De Educación Secundaria Nº 5": TipoEntidad.ESCUELA_SECUNDARIA,
            "Escuela Especial Nº 501": TipoEntidad.ESCUELA_ESPECIAL,
        }
        for nombre, esperado in casos.items():
            with self.subTest(nombre=nombre):
                self.assertIs(clasificar({"amenity": "school", "name": nombre}), esperado)

    def test_escuela_sin_pista_no_se_inventa_el_nivel(self):
        """ADR-0009: si no se sabe el nivel, se dice que no se sabe."""
        self.assertIs(
            clasificar({"amenity": "school", "name": "Escuela Nº 45"}),
            TipoEntidad.ESCUELA_SIN_CLASIFICAR,
        )

    def test_gobierno_y_territorio(self):
        self.assertIs(clasificar({"amenity": "townhall"}), TipoEntidad.MUNICIPALIDAD)
        self.assertIs(clasificar({"amenity": "police"}), TipoEntidad.POLICIA)
        self.assertIs(clasificar({"place": "neighbourhood"}), TipoEntidad.BARRIO)
        self.assertIs(clasificar({"place": "suburb"}), TipoEntidad.BARRIO)

    def test_lo_desconocido_queda_como_otro(self):
        self.assertIs(clasificar({"amenity": "bench"}), TipoEntidad.OTRO)


class TestEntidad(unittest.TestCase):
    def test_lleva_su_procedencia(self):
        e = entidad()
        self.assertEqual(e.fuente, FuenteEntidad.OSM)
        self.assertEqual(e.id_en_fuente, "node/123456")
        self.assertTrue(e.ubicada)

    def test_id_estable_por_fuente_y_referencia(self):
        self.assertEqual(entidad().id, entidad(nombre="Otro nombre").id)

    def test_coordenada_fuera_de_argentina_no_entra(self):
        """Mejor que falle a que quede un hospital en Asia."""
        with self.assertRaises(ValidationError):
            entidad(latitud=48.85, longitud=2.35)  # París

    def test_una_entidad_sin_coordenadas_sigue_siendo_valida(self):
        e = entidad(latitud=None, longitud=None)
        self.assertFalse(e.ubicada)

    def test_plazas_y_clubes_exigen_nombre(self):
        """226 poligonos de 'equipamiento comunitario' sin nombre ahogaban el
        censo de Chascomus."""
        self.assertIn(TipoEntidad.PLAZA, REQUIEREN_NOMBRE)
        self.assertIn(TipoEntidad.OTRO, REQUIEREN_NOMBRE)

    def test_salud_y_educacion_no_exigen_nombre(self):
        """Un CAPS sin rotular sigue siendo un CAPS que hay que ir a ver."""
        for tipo in (TipoEntidad.CAPS, TipoEntidad.HOSPITAL, TipoEntidad.ESCUELA_PRIMARIA):
            self.assertNotIn(tipo, REQUIEREN_NOMBRE)


class TestCenso(unittest.TestCase):
    def _censo(self):
        return CensoMunicipio(
            municipio="Chascomús", id_municipio="MUN-BA-001", osm_id=5816495, fecha=FECHA,
            entidades=[
                entidad(),
                entidad(tipo=TipoEntidad.CAPS, nombre="CAPS IPORA", id_en_fuente="node/2"),
                entidad(tipo=TipoEntidad.FARMACIA, nombre="Bellingeri", id_en_fuente="node/3"),
                entidad(tipo=TipoEntidad.BARRIO, nombre="Villa Jardín", id_en_fuente="node/4"),
            ],
        )

    def test_agrupa_por_capas_como_un_mapa(self):
        capas = self._censo().por_capa()
        self.assertEqual(len(capas["Salud"]), 3)
        self.assertEqual(len(capas["Territorio"]), 1)
        self.assertNotIn("Educación", capas)  # no se inventan capas vacias

    def test_resumen_cuenta_lo_ubicado_y_lo_nombrado(self):
        r = self._censo().resumen()
        self.assertEqual(r["total"], 4)
        self.assertEqual(r["ubicadas"], 4)
        self.assertEqual(r["por_tipo"]["caps"], 1)

    def test_todas_las_capas_del_catalogo_tienen_tipos(self):
        for capa, tipos in CAPAS.items():
            with self.subTest(capa=capa):
                self.assertTrue(tipos)


if __name__ == "__main__":
    unittest.main(verbosity=2)
