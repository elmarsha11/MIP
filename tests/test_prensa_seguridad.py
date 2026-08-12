"""
Tests del eje 2: que tiene y como opera cada municipio, leido de la prensa.

Lo que se fija es que la prensa no pueda meter en un municipio algo que no le
corresponde. Son tres formas de equivocarse y las tres ya pasaron en el proyecto:
atribuirle una nota de otra ciudad, aceptar una cita que no prueba lo que se
afirma, y contar dos veces la misma nota.
"""

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
for _ruta in (_RAIZ / "src" / "seguridad", _RAIZ / "src" / "extraction",
              _RAIZ / "src" / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from operativos import (  # noqa: E402
    NOTAS_POR_ASPECTO,
    armar_texto,
    cita_prueba_aspecto,
    verificar_respuesta,
)
from prensa import CONSULTAS, Nota, es_del_municipio  # noqa: E402


def _nota(titulo, texto, aspecto="centro_monitoreo", fecha="2026-08-01", url=None):
    return Nota(
        medio="El Fuerte Diario", url_medio="https://elfuertediario.com.ar/",
        aspecto=aspecto, termino="camaras de seguridad", titulo=titulo,
        fecha=fecha, url=url or f"https://elfuertediario.com.ar/{abs(hash(titulo))}",
        texto=texto,
    )


class TestLaNotaEsDelMunicipio(unittest.TestCase):
    """Un municipio no puede heredar los operativos de otro."""

    def test_medio_local_acepta_sin_nombrar_al_pueblo(self):
        """La primera version exigia el nombre y de 252 notas dejaba 39.

        Entre las descartadas estaba "operativos de control en la laguna", que es
        el simbolo de Chascomus: un diario local escribe para sus vecinos y dice
        "la ciudad", no repite el nombre del pueblo en cada nota.
        """
        n = _nota("Operativos de control en la laguna", "Se incautaron 15 redes.")
        self.assertTrue(es_del_municipio(n, "Chascomús"))

    def test_medio_local_descarta_la_republicacion(self):
        """El Fuerte Diario, de Chascomus, publica noticias de Mar del Plata."""
        n = _nota("Mar del Plata: refuerzan la seguridad tras reclamos", "En la costa...")
        self.assertFalse(es_del_municipio(n, "Chascomús"))

    def test_medio_regional_exige_el_nombre(self):
        """Infozona cubre cuatro partidos: estar publicado ahi no dice de cual."""
        n = _nota("Detuvieron a dos personas", "Ocurrio en la zona rural.")
        self.assertFalse(es_del_municipio(n, "Chascomús", regional=True))
        con_nombre = _nota("Detuvieron a dos personas", "Ocurrio en Chascomús.")
        self.assertTrue(es_del_municipio(con_nombre, "Chascomús", regional=True))

    def test_el_nombre_corto_alcanza(self):
        """La prensa de General Madariaga dice "Madariaga" a secas."""
        n = _nota("Nuevo operativo", "La policia de Madariaga trabajo en la zona.")
        self.assertTrue(es_del_municipio(n, "General Madariaga", regional=True))


class TestLaCitaPruebaElAspecto(unittest.TestCase):
    """El guard que en el gabinete evito que un nombre suelto entrara como cargo."""

    def test_una_cita_concreta_prueba(self):
        self.assertTrue(cita_prueba_aspecto(
            "El Centro de Monitoreo Municipal permitio identificar al conductor",
            "centro_monitoreo"))
        self.assertTrue(cita_prueba_aspecto(
            "se llevaron adelante dos allanamientos en el barrio", "allanamientos"))

    def test_hablar_del_tema_no_prueba(self):
        """"El intendente hablo de seguridad" menciona el tema y no prueba que
        exista un centro de monitoreo."""
        self.assertFalse(cita_prueba_aspecto(
            "El intendente hablo de seguridad con los vecinos", "centro_monitoreo"))
        self.assertFalse(cita_prueba_aspecto(
            "La seguridad es una preocupacion central", "allanamientos"))

    def test_un_aspecto_no_prueba_a_otro(self):
        """Que exista una comisaria no significa que haya patrulla urbana
        municipal: son cosas distintas y las paga gente distinta."""
        self.assertTrue(cita_prueba_aspecto(
            "permanece detenido en la comisaria", "policia_bonaerense"))
        self.assertFalse(cita_prueba_aspecto(
            "permanece detenido en la comisaria", "patrulla_urbana"))


class TestVerificacion(unittest.TestCase):
    def setUp(self):
        self.nota = _nota(
            "Secuestraron una motocicleta",
            "El Centro de Monitoreo Municipal permitio recopilar los registros filmicos.",
        )
        self.indice = {"1": self.nota}

    def _resp(self, **kw):
        item = {
            "aspecto": "centro_monitoreo", "presente": "si",
            "detalle": "El municipio tiene centro de monitoreo con camaras.",
            "cita_literal": "El Centro de Monitoreo Municipal permitio recopilar los registros filmicos.",
        }
        item.update(kw)
        return {"aspectos": [item], "_modelo": "deepseek-chat"}

    def test_la_cita_literal_sobrevive(self):
        ok, rech = verificar_respuesta(self._resp(), "X", "x-1", self.indice, "2026-08-12")
        self.assertEqual(len(ok), 1)
        self.assertEqual(rech, 0)
        self.assertEqual(ok[0]["aspecto"], "centro_monitoreo")
        self.assertEqual(ok[0]["url"], self.nota.url)

    def test_la_cita_inventada_se_rechaza(self):
        resp = self._resp(cita_literal="El municipio compro 200 camaras nuevas.")
        ok, rech = verificar_respuesta(resp, "X", "x-1", self.indice, "2026-08-12")
        self.assertEqual((ok, rech), ([], 1))

    def test_la_cita_real_que_no_prueba_el_aspecto_se_rechaza(self):
        resp = self._resp(aspecto="fuerzas_federales")
        ok, rech = verificar_respuesta(resp, "X", "x-1", self.indice, "2026-08-12")
        self.assertEqual((ok, rech), ([], 1))

    def test_no_verificable_no_entra_ni_cuenta_como_rechazo(self):
        """Un vacio honesto es una respuesta correcta, no un fracaso."""
        resp = self._resp(presente="no_verificable", cita_literal="")
        ok, rech = verificar_respuesta(resp, "X", "x-1", self.indice, "2026-08-12")
        self.assertEqual((ok, rech), ([], 0))

    def test_un_aspecto_una_sola_vez(self):
        resp = self._resp()
        resp["aspectos"].append(dict(resp["aspectos"][0]))
        ok, _ = verificar_respuesta(resp, "X", "x-1", self.indice, "2026-08-12")
        self.assertEqual(len(ok), 1)

    def test_respuesta_none_no_rompe(self):
        self.assertEqual(verificar_respuesta(None, "X", "x-1", {}, "f"), ([], 0))


class TestArmadoDelTexto(unittest.TestCase):
    def test_se_limita_por_aspecto(self):
        """Un medio puede tener 200 notas locales en 12 meses: mandarlas todas es
        medio millon de caracteres para responder siete preguntas."""
        notas = [
            _nota(f"Nota {i}", "El centro de monitoreo funciona.", fecha=f"2026-0{i%9+1}-01")
            for i in range(20)
        ]
        texto, indice = armar_texto(notas)
        self.assertEqual(len(indice), NOTAS_POR_ASPECTO)

    def test_no_repite_la_misma_nota(self):
        n = _nota("Unica", "El centro de monitoreo funciona.")
        texto, indice = armar_texto([n, n, n])
        self.assertEqual(len(indice), 1)

    def test_cada_aspecto_tiene_su_cupo(self):
        notas = [
            _nota(f"N{a}", "texto", aspecto=a) for a in list(CONSULTAS)[:4]
        ]
        _, indice = armar_texto(notas)
        self.assertEqual(len(indice), 4)


if __name__ == "__main__":
    unittest.main()
