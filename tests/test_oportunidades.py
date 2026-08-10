"""
Tests del motor comercial.

Los casos no son inventados: casi todos salieron de corridas reales sobre
Navarro, Ayacucho, Castelli y Pinamar el 2026-08-09, incluidos los falsos
positivos que hubo que matar.
"""

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
for _ruta in (
    _RAIZ / "src" / "oportunidades",
    _RAIZ / "src" / "extraction",
    _RAIZ / "src" / "discovery",
):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from catalogo import Area, Friccion  # noqa: E402
from detector import verificar_respuesta  # noqa: E402
from comercial import MunicipioOportunidades, Oportunidad  # noqa: E402
from friccion import conciliar, friccion_probada  # noqa: E402


class PaginaFalsa:
    """Sustituye a fetcher.Pagina sin salir a la red."""

    def __init__(self, texto, url="https://x.gob.ar/", tipo="portal"):
        self.texto = texto
        self.url = url
        self.tipo = tipo
        self.confianza_url = "Alta"


class TestFriccionProbada(unittest.TestCase):
    """El codigo decide si la cita prueba friccion. El modelo solo propone."""

    def test_instruccion_presencial_es_alta(self):
        cita = "dirigirse a la Mesa de Entradas del Hospital Municipal."
        self.assertIs(friccion_probada(cita), Friccion.ALTA)

    def test_orden_de_llegada_es_alta(self):
        cita = "Las vacunaciones se realizan de lunes a viernes de 8 a 18, por orden de llegada"
        self.assertIs(friccion_probada(cita), Friccion.ALTA)

    def test_consultorios_externos_con_telefono_es_alta(self):
        """El caso de Navarro.

        No hay verbo en la cita, pero un consultorio externo publicado con su
        telefono ES el mostrador de turnos: el vecino llama y alguien anota a
        mano. Sin esta regla la oportunidad de mayor valor comercial quedaba
        rankeada como media.
        """
        cita = "CONSULTORIOS EXTERNOS 2272-400663 / 2272-430668"
        self.assertIs(friccion_probada(cita), Friccion.ALTA)

    def test_telefono_suelto_es_media(self):
        self.assertIs(friccion_probada("Teléfono: (02227) 49-1054"), Friccion.MEDIA)

    def test_texto_sin_accion_manual_no_prueba_nada(self):
        """El falso positivo mas comun: 'no dice que sea digital' no es friccion.

        Salio de Navarro: el modelo proponia oportunidades citando titulos de
        seccion. Inferir desde la ausencia es lo que ADR-0009 prohibe.
        """
        for cita in (
            "Licitaciones - Oficina de Compras",
            "Dirección de Educación Visitar sitio",
            "Habilitación de Comercios Ingresar",
        ):
            with self.subTest(cita=cita):
                self.assertIsNone(friccion_probada(cita))

    def test_cita_que_muestra_canal_digital_no_es_oportunidad(self):
        """Si ya esta digitalizado, no hay nada que vender."""
        for cita in (
            "Si tenes una mascota peligrosa, debés registrarte en el siguiente link: Registrarme",
            "Botón de pago online Ingresa al servicio tasas municipales",
            "Reclamo General Sistema Web de Reclamos CCA Whatsapp: 2254-585415",
        ):
            with self.subTest(cita=cita):
                self.assertIsNone(friccion_probada(cita))

    def test_lo_digital_gana_sobre_la_accion_manual(self):
        """Una cita mixta no es oportunidad: el municipio ya tiene el sistema.

        Pinamar listaba telefono y whatsapp de reclamos y adentro decia "Sistema
        Web de Reclamos". Contarlo como oportunidad seria venderle lo que ya tiene.
        """
        cita = "Reclamo General Sistema Web de Reclamos CCA Tel: 491613"
        self.assertIsNone(friccion_probada(cita))

    def test_cita_muy_corta_se_descarta(self):
        self.assertIsNone(friccion_probada("turnos"))
        self.assertIsNone(friccion_probada(""))


class TestConciliar(unittest.TestCase):
    def test_gana_la_mas_conservadora(self):
        self.assertIs(conciliar(Friccion.ALTA, Friccion.MEDIA), Friccion.MEDIA)
        self.assertIs(conciliar(Friccion.MEDIA, Friccion.ALTA), Friccion.MEDIA)
        self.assertIs(conciliar(Friccion.ALTA, Friccion.ALTA), Friccion.ALTA)


class TestVerificarRespuesta(unittest.TestCase):
    """ADR-0014 en la capa comercial: la cita tiene que existir literal."""

    def setUp(self):
        self.paginas = [
            PaginaFalsa(
                "Hospital Municipal. Por consultas sobre turnos para especialidades, "
                "dirigirse a la Mesa de Entradas del Hospital Municipal.",
                url="https://x.gob.ar/hospital",
            )
        ]

    def _resp(self, **kw):
        item = {
            "area": "salud",
            "problema": "Hay que ir en persona a sacar turno.",
            "friccion": "alta",
            "cita_literal": "dirigirse a la Mesa de Entradas del Hospital Municipal.",
            "pagina": 1,
        }
        item.update(kw)
        return {"oportunidades": [item], "_modelo": "deepseek-chat"}

    def test_cita_literal_sobrevive(self):
        ops, rechazadas = verificar_respuesta(self._resp(), "X", "x-1", self.paginas, "2026-08-09")
        self.assertEqual(len(ops), 1)
        self.assertEqual(rechazadas, 0)
        self.assertIs(ops[0].area, Area.SALUD)
        self.assertIs(ops[0].friccion, Friccion.ALTA)
        self.assertEqual(ops[0].url, "https://x.gob.ar/hospital")

    def test_cita_inventada_se_rechaza(self):
        resp = self._resp(cita_literal="Los turnos se sacan por la app municipal.")
        ops, rechazadas = verificar_respuesta(resp, "X", "x-1", self.paginas, "2026-08-09")
        self.assertEqual(ops, [])
        self.assertEqual(rechazadas, 1)

    def test_numero_de_pagina_equivocado_no_invalida_la_cita(self):
        """Errarle a la pagina es un desliz; inventar la cita no."""
        ops, _ = verificar_respuesta(self._resp(pagina=99), "X", "x-1", self.paginas, "2026-08-09")
        self.assertEqual(len(ops), 1)

    def test_area_fuera_del_catalogo_se_rechaza(self):
        ops, rechazadas = verificar_respuesta(
            self._resp(area="deportes"), "X", "x-1", self.paginas, "2026-08-09"
        )
        self.assertEqual(ops, [])
        self.assertEqual(rechazadas, 1)

    def test_una_sola_oportunidad_por_area(self):
        resp = self._resp()
        resp["oportunidades"].append(dict(resp["oportunidades"][0]))
        ops, _ = verificar_respuesta(resp, "X", "x-1", self.paginas, "2026-08-09")
        self.assertEqual(len(ops), 1)

    def test_una_cita_no_sirve_para_dos_areas(self):
        """Carmen de Areco quedaba primero en el ranking por esto.

        "Mesa de entradas Moreno 541" probaba tramites Y expedientes: dos
        oportunidades de una sola evidencia. El puntaje inflado manda al equipo
        comercial al municipio equivocado.
        """
        resp = self._resp()
        gemelo = dict(resp["oportunidades"][0])
        gemelo["area"] = "expedientes"
        resp["oportunidades"].append(gemelo)
        ops, _ = verificar_respuesta(resp, "X", "x-1", self.paginas, "2026-08-09")
        self.assertEqual(len(ops), 1)
        self.assertIs(ops[0].area, Area.SALUD)

    def test_respuesta_vacia_no_es_error(self):
        """Un municipio sin procesos manuales probados es una respuesta valida."""
        ops, rechazadas = verificar_respuesta(
            {"oportunidades": []}, "X", "x-1", self.paginas, "2026-08-09"
        )
        self.assertEqual(ops, [])
        self.assertEqual(rechazadas, 0)

    def test_respuesta_none_no_rompe(self):
        ops, rechazadas = verificar_respuesta(None, "X", "x-1", self.paginas, "2026-08-09")
        self.assertEqual(ops, [])
        self.assertEqual(rechazadas, 0)


class TestPuntaje(unittest.TestCase):
    def _op(self, area, friccion):
        return Oportunidad(
            municipio="X", id_municipio="x-1", area=area, problema="p",
            friccion=friccion, cita="c" * 20, url="u", producto="prod",
            fecha="2026-08-09",
        )

    def test_una_alta_pesa_mas_que_dos_bajas(self):
        """Si no, un municipio con indicios sueltos le gana a uno con friccion
        probada, y el equipo comercial visita al equivocado."""
        alta = MunicipioOportunidades(
            municipio="A", id_municipio="a", fecha="f", paginas_leidas=1,
            caracteres_analizados=1, oportunidades=[self._op(Area.SALUD, Friccion.ALTA)],
        )
        bajas = MunicipioOportunidades(
            municipio="B", id_municipio="b", fecha="f", paginas_leidas=1,
            caracteres_analizados=1,
            oportunidades=[
                self._op(Area.SALUD, Friccion.BAJA),
                self._op(Area.TURISMO, Friccion.BAJA),
            ],
        )
        self.assertGreater(alta.puntaje(), bajas.puntaje())

    def test_id_es_determinista(self):
        """Re-correr no puede duplicar filas."""
        a, b = self._op(Area.SALUD, Friccion.ALTA), self._op(Area.SALUD, Friccion.ALTA)
        self.assertEqual(a.id, b.id)


if __name__ == "__main__":
    unittest.main()
