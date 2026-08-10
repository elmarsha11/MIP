"""
Tests del motor de gabinete.

Los casos salen de la corrida real sobre Chascomus del 2026-08-09, incluidos los
falsos positivos que hubo que matar y el recorte que perdia secretarias.
"""

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
for _ruta in (
    _RAIZ / "src" / "gabinete",
    _RAIZ / "src" / "extraction",
    _RAIZ / "src" / "discovery",
):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from autoridades import Autoridad, Cargo, TipoFuente  # noqa: E402
from lector import fecha_de_la_norma, recortar, verificar_respuesta  # noqa: E402
from nombres import motivo_del_rechazo, nombre_valido_en_cita  # noqa: E402

FIRMA = (
    "ARTÍCULO 3°.- El presente Decreto será refrendado por el Secretario de "
    "Obras, Servicios Públicos y Ambiente (Lucas Funes).- ARTÍCULO 4º.- Cúmplase."
)


class FuenteFalsa:
    def __init__(self, texto, url="https://sibom.slyt.gba.gob.ar/bulletins/1"):
        self.texto = texto
        self.url = url


class TestNombreEnContexto(unittest.TestCase):
    """El guard que no existia en ningun otro modulo de MIP."""

    def test_firma_de_decreto_es_valida(self):
        self.assertTrue(nombre_valido_en_cita("Lucas Funes", FIRMA))

    def test_intendente_en_nota_de_prensa_es_valido(self):
        cita = "el Intendente Municipal, Javier Osuna junto al Director del Hospital"
        self.assertTrue(nombre_valido_en_cita("Javier Osuna", cita))

    def test_nombre_que_bautiza_un_caps_se_rechaza(self):
        """El caso que motivo el modulo.

        "Centro de Salud Intendente Pedro Carossi" es un edificio con el nombre de
        un intendente anterior. La cita es literal y el nombre esta adentro: los
        dos guards que ya tenia MIP la dejaban pasar.
        """
        for cita in (
            'Centro de Salud "Intendente Pedro Carossi" Ricardo Rojas 197',
            "Centro de Salud Intendente Pedro Carossi, Ricardo Rojas 197",
        ):
            with self.subTest(cita=cita):
                self.assertFalse(nombre_valido_en_cita("Pedro Carossi", cita))

    def test_titulo_intercalado_no_salva_al_edificio(self):
        """"Escuela Doctor Rene Favaloro": la palabra-cosa no queda pegada al
        nombre, y sin contemplar el titulo el filtro no enganchaba."""
        self.assertFalse(nombre_valido_en_cita("Rene Favaloro", "Escuela Doctor Rene Favaloro"))

    def test_un_nombre_valido_convive_con_un_edificio(self):
        cita = "El intendente Javier Gaston encabezo el acto en la Escuela Domingo Sarmiento"
        self.assertTrue(nombre_valido_en_cita("Javier Gaston", cita))
        self.assertFalse(nombre_valido_en_cita("Domingo Sarmiento", cita))

    def test_apellido_suelto_no_identifica(self):
        self.assertFalse(nombre_valido_en_cita("Funes", FIRMA))

    def test_nombre_ausente_de_la_cita(self):
        self.assertFalse(nombre_valido_en_cita("Juan Perez", "obras de bacheo en el barrio Belgrano"))
        self.assertEqual(
            motivo_del_rechazo("Juan Perez", "obras de bacheo en el barrio Belgrano"),
            "el nombre no esta en la cita",
        )


class TestRecorte(unittest.TestCase):
    def test_extrae_la_firma_sin_el_decreto_alrededor(self):
        texto = "x" * 5000 + FIRMA + "y" * 5000
        r = recortar(texto)
        self.assertIn("Lucas Funes", r)
        self.assertLess(len(r), 3000)

    def test_no_repite_la_misma_firma(self):
        """Un boletin trae ~70 firmas de apenas 5 personas."""
        texto = (FIRMA + " relleno. ") * 40
        r = recortar(texto)
        self.assertEqual(r.count("Lucas Funes"), 1)

    def test_la_firma_multiple_sobrevive_al_presupuesto(self):
        """El bug que perdia 3 de 8 secretarias.

        Moscarella aparece 2 veces en 773.000 caracteres, dentro de un decreto
        con tres firmantes y muy tarde en el documento. Mandando el decreto
        entero alrededor de cada firma, el presupuesto se agotaba antes.
        """
        multiple = (
            "El presente Decreto será refrendado por el Secretario de Gobierno "
            "(Cipriano Pérez del Cerro), la Secretaria de Seguridad Ciudadana "
            "(Mariela Moscarella) y la Secretaria de Salud Pública (Marcela Arias)."
        )
        texto = (FIRMA + " relleno largo. " * 50) * 60 + multiple
        r = recortar(texto)
        self.assertIn("Mariela Moscarella", r)


class TestVerificacion(unittest.TestCase):
    def setUp(self):
        self.fuentes = [FuenteFalsa(FIRMA)]

    def _resp(self, **kw):
        item = {
            "cargo": "secretario",
            "area": "Obras, Servicios Públicos y Ambiente",
            "nombre": "Lucas Funes",
            "cita_literal": "refrendado por el Secretario de Obras, Servicios Públicos y Ambiente (Lucas Funes)",
        }
        item.update(kw)
        return {"autoridades": [item], "_modelo": "deepseek-chat"}

    def test_firma_verificada_sobrevive(self):
        a, r = verificar_respuesta(self._resp(), "X", "x-1", self.fuentes, "2026-08-09")
        self.assertEqual(len(a), 1)
        self.assertEqual(r, 0)
        self.assertEqual(a[0].nombre, "Lucas Funes")
        self.assertIs(a[0].cargo, Cargo.SECRETARIO)
        self.assertEqual(a[0].confianza, "Alta")

    def test_cita_inventada_se_rechaza(self):
        resp = self._resp(cita_literal="El Secretario de Obras es Jorge Marino")
        a, r = verificar_respuesta(resp, "X", "x-1", self.fuentes, "2026-08-09")
        self.assertEqual(a, [])
        self.assertEqual(r, 1)

    def test_cita_real_pero_sin_el_nombre_se_rechaza(self):
        """La trampa del handoff §7 aplicada aca: la cita existe, pero no prueba
        que esa persona ocupe el cargo."""
        resp = self._resp(nombre="Jorge Marino", cita_literal="ARTÍCULO 4º.- Cúmplase.")
        a, r = verificar_respuesta(resp, "X", "x-1", self.fuentes, "2026-08-09")
        self.assertEqual(a, [])
        self.assertEqual(r, 1)

    def test_el_intendente_no_lleva_area(self):
        resp = self._resp(cargo="intendente", area="Gobierno")
        a, _ = verificar_respuesta(resp, "X", "x-1", self.fuentes, "2026-08-09")
        self.assertEqual(len(a), 1)
        self.assertIsNone(a[0].area)

    def test_no_hay_dos_secretarios_de_la_misma_area(self):
        resp = self._resp()
        gemelo = dict(resp["autoridades"][0])
        gemelo["nombre"] = "Jorge Marino"
        resp["autoridades"].append(gemelo)
        a, _ = verificar_respuesta(resp, "X", "x-1", self.fuentes, "2026-08-09")
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0].nombre, "Lucas Funes")

    def test_respuesta_vacia_es_valida(self):
        a, r = verificar_respuesta({"autoridades": []}, "X", "x-1", self.fuentes, "2026-08-09")
        self.assertEqual((a, r), ([], 0))

    def test_respuesta_none_no_rompe(self):
        a, r = verificar_respuesta(None, "X", "x-1", self.fuentes, "2026-08-09")
        self.assertEqual((a, r), ([], 0))


class TestFechaDeLaNorma(unittest.TestCase):
    """Sin la fecha del decreto, la base no distingue quien ESTA de quien ESTUVO."""

    def test_toma_el_encabezado_del_decreto(self):
        texto = "Decreto Nº 526/26 Chascomús, 29/06/2026 VISTO ... " + FIRMA
        self.assertEqual(
            fecha_de_la_norma(texto, texto.index("refrendado")), "2026-06-29"
        )

    def test_descarta_fechas_futuras(self):
        """El bug del "decreto del 2029-05-02".

        Un decreto menciona fechas que no son la suya: vencimientos de contrato,
        plazos de obra, licencias "hasta el 13/07/2029". La mas cercana hacia
        atras podia ser una de esas.
        """
        texto = "Chascomús, 01/06/2026 ... plazo de obra hasta el 02/05/2029 .- " + FIRMA
        self.assertEqual(
            fecha_de_la_norma(texto, texto.index("refrendado"), tope="2026-08-09"),
            "2026-06-01",
        )

    def test_descarta_fechas_anteriores_a_sibom(self):
        texto = "ordenanza de 12/03/1998 ... " + FIRMA
        self.assertIsNone(fecha_de_la_norma(texto, texto.index("refrendado")))

    def test_sin_fecha_devuelve_none(self):
        self.assertIsNone(fecha_de_la_norma(FIRMA, 0))


class TestGabineteQueCambia(unittest.TestCase):
    """El caso Marino/Funes: dos citas literales, las dos correctas."""

    def _fuente(self):
        return FuenteFalsa(
            "Decreto Nº 300/26 Chascomús, 15/04/2026 VISTO ... El presente Decreto será "
            "refrendado por el Secretario de Obras, Servicios Públicos y Ambiente "
            "(Jorge Marino).- Cúmplase. "
            "Decreto Nº 500/26 Chascomús, 02/06/2026 VISTO ... El presente Decreto será "
            "refrendado por el Secretario de Obras, Servicios Públicos y Ambiente "
            "(Lucas Funes).- Cúmplase."
        )

    def _resp(self):
        base = {"cargo": "secretario", "area": "Obras, Servicios Públicos y Ambiente"}
        return {
            "autoridades": [
                dict(base, nombre="Jorge Marino",
                     cita_literal="refrendado por el Secretario de Obras, Servicios Públicos y Ambiente (Jorge Marino)"),
                dict(base, nombre="Lucas Funes",
                     cita_literal="refrendado por el Secretario de Obras, Servicios Públicos y Ambiente (Lucas Funes)"),
            ],
            "_modelo": "deepseek-chat",
        }

    def test_gana_el_decreto_mas_nuevo(self):
        a, _ = verificar_respuesta(
            self._resp(), "Chascomús", "c-1", [self._fuente()], "2026-08-09"
        )
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0].nombre, "Lucas Funes")
        self.assertEqual(a[0].fecha_norma, "2026-06-02")

    def test_el_orden_de_la_respuesta_no_decide(self):
        """Quedarse con el primero seria quedarse con el que la suerte ponga."""
        resp = self._resp()
        resp["autoridades"].reverse()
        a, _ = verificar_respuesta(
            resp, "Chascomús", "c-1", [self._fuente()], "2026-08-09"
        )
        self.assertEqual(a[0].nombre, "Lucas Funes")


class TestConfianzaPorFuente(unittest.TestCase):
    def _aut(self, fuente):
        return Autoridad(
            municipio="X", id_municipio="x-1", cargo=Cargo.SECRETARIO, area="Gobierno",
            nombre="Lucas Funes", cita=FIRMA, url="u", fuente=fuente, fecha="2026-08-09",
        )

    def test_el_boletin_vale_mas_que_la_red_social(self):
        self.assertEqual(self._aut(TipoFuente.BOLETIN_OFICIAL).confianza, "Alta")
        self.assertEqual(self._aut(TipoFuente.PORTAL).confianza, "Media")
        self.assertEqual(self._aut(TipoFuente.RED_OFICIAL).confianza, "Baja")

    def test_id_determinista_por_cargo_y_area(self):
        """Re-correr no duplica, y un secretario nuevo reemplaza al anterior en
        la misma area en vez de convivir con el."""
        a = self._aut(TipoFuente.BOLETIN_OFICIAL)
        b = self._aut(TipoFuente.BOLETIN_OFICIAL).model_copy(update={"nombre": "Jorge Marino"})
        self.assertEqual(a.id, b.id)


if __name__ == "__main__":
    unittest.main()
