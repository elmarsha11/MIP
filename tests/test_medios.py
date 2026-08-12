"""
Tests del catalogo de medios.

La semilla la releva Juli a mano y no hay fuente automatica que la reemplace,
asi que lo que se prueba es que el codigo no la degrade: que no cruce municipios,
que no cuente un canal oficial como prensa independiente, y que no invente una
URL que no corresponde al medio.
"""

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
for _ruta in (_RAIZ / "src" / "medios", _RAIZ / "src" / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

import catalogo_medios  # noqa: E402
from catalogo_medios import NO_SON_MEDIOS, leer, regionales  # noqa: E402
from resolver import _parecido, candidatos  # noqa: E402


class TestSemilla(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.medios = leer()

    def test_cubre_los_86(self):
        self.assertEqual(len({m.municipio for m in self.medios}), 86)

    def test_el_id_sale_del_gold_standard_y_no_del_csv(self):
        """El CSV trae la columna ID_Municipios CORRIDA.

        Los 86 nombres matchean, pero 46 filas dan un id que no corresponde: el
        archivo pone MUN-BA-041 para Pinamar y el Gold Standard dice
        MUN-BA-042, desplazado uno de ahi en adelante. Cruzar por ese id le daria
        a 46 municipios los medios del vecino.
        """
        from discovery_engine import cargar_municipios

        gold = {m.nombre: m.id_municipio for m in cargar_municipios()}
        for m in self.medios:
            with self.subTest(municipio=m.municipio):
                self.assertEqual(m.id_municipio, gold[m.municipio])

    def test_un_canal_oficial_no_cuenta_como_prensa_independiente(self):
        """"Tapalqué SIBOM" es el boletin oficial y "General Belgrano Gobierno
        Municipal" es el municipio. Contarlos como alternativos haria parecer que
        alguien controla al municipio cuando no hay nadie."""
        for m in self.medios:
            if m.nombre in NO_SON_MEDIOS:
                with self.subTest(nombre=m.nombre):
                    self.assertEqual(m.tipo, "oficial")

    def test_el_mismo_medio_no_cuenta_dos_veces_por_como_se_escribe(self):
        """"InfoZona" e "Infozona" son el mismo medio."""
        nombres = {m.nombre for m in self.medios if m.tipo == "alternativo"}
        normalizados = {catalogo_medios._normalizar(n) for n in nombres}
        self.assertEqual(len(nombres), len(normalizados))

    def test_los_regionales_se_detectan(self):
        """Un medio que cubre varios partidos sirve para varios, pero al contar
        hechos hay que evitar sumar la misma nota dos veces."""
        r = regionales(self.medios)
        self.assertIn("Infozona", r)
        self.assertGreater(len(r["Infozona"]), 1)


class TestCandidatos(unittest.TestCase):
    def test_prueba_http_ademas_de_https(self):
        """ADR-0012: se admite http, hay sitios sin TLS y eso es un dato.

        El resolver lo ignoraba y bolivarhoy.com.ar quedaba como "ningun dominio
        responde" teniendo sitio: existe, pero solo por http.
        """
        urls = candidatos("Bolivarhoy")
        self.assertIn("https://bolivarhoy.com.ar", urls)
        self.assertIn("http://bolivarhoy.com.ar", urls)

    def test_genera_la_forma_sin_palabras_genericas(self):
        """"El Fuerte Diario" puede ser elfuertediario.com.ar o elfuerte.com.ar."""
        urls = " ".join(candidatos("El Fuerte Diario"))
        self.assertIn("elfuertediario.com.ar", urls)
        self.assertIn("elfuerte.com.ar", urls)

    def test_corta_el_sufijo_regional_del_nombre(self):
        """"La Región Web - Guaminí" es el mismo medio que cubre otro partido:
        el dominio es el del medio, no el del partido."""
        urls = " ".join(candidatos("La Región Web - Guaminí"))
        self.assertIn("laregionweb.com.ar", urls)
        self.assertNotIn("guamini", urls)

    def test_un_nombre_vacio_no_genera_nada(self):
        self.assertEqual(candidatos(""), [])


class TestValidacionPorTitulo(unittest.TestCase):
    """Sin esto entran dominios parkeados, que responden 200 para cualquier nombre."""

    def test_acepta_el_titulo_del_medio(self):
        self.assertTrue(_parecido("EL FUERTE DIARIO", "El Fuerte Diario"))
        self.assertTrue(_parecido("INFOZONA - Últimas Noticias", "Infozona"))

    def test_rechaza_un_dominio_parkeado(self):
        self.assertFalse(_parecido("Dominio en venta - Comprar ahora", "El Fuerte Diario"))

    def test_coincidir_en_una_palabra_generica_no_alcanza(self):
        """Casi todo medio se llama "Diario X" o "X Noticias": coincidir en
        "diario" no prueba que sea el mismo medio."""
        self.assertFalse(_parecido("Diario Popular", "Diario Suipacha"))
        self.assertFalse(_parecido("Noticias Argentinas", "Navarro Noticias"))


if __name__ == "__main__":
    unittest.main()
