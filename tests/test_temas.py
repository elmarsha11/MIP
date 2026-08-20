"""
Tests del motor de temas.

No salen a la red ni llaman a la IA: usan paginas falsas y respuestas de modelo
fijas. Los casos del tema ambiental son los modos concretos de equivocarse que
motivaron cada guard, sobre todo el de tercera categoria: por Ley 11.459 el
Certificado de Aptitud Ambiental lo emite OPDS, asi que la pagina que mejor
explica el tramite es la que peor prueba que lo haga el municipio.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
for _ruta in (
    _RAIZ / "src" / "temas",
    _RAIZ / "src" / "extraction",
    _RAIZ / "src" / "discovery",
):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from cosecha import (  # noqa: E402
    PaginaTema,
    boletines_del_municipio,
    enlaces_del_tema,
    fragmentos_relevantes,
)
from definiciones import TEMA_AMBIENTAL, ids_temas, tema  # noqa: E402
from guardas import (  # noqa: E402
    clasificar,
    conciliar,
    es_anuncio_a_futuro,
    menciona_al_municipio,
    menciona_organismo_ajeno,
)
from interrogador import verificar_respuesta  # noqa: E402
from rastreo import Estado, HallazgoTema, MunicipioTema, SubTema, TipoEvidencia  # noqa: E402

PROMOTORES = TEMA_AMBIENTAL.subtema("promotores_ambientales")
FISCALIZACION = TEMA_AMBIENTAL.subtema("fiscalizacion_3ra")
ACCIONES = TEMA_AMBIENTAL.subtema("acciones_ambientales")


def pagina(texto, url="https://x.gob.ar/", tipo="sitio_oficial", evidencia=TipoEvidencia.OFICIAL):
    return PaginaTema(
        url=url, tipo=tipo, confianza_url="Alta", texto=texto, tipo_evidencia=evidencia
    )


# ---------------------------------------------------------------------------
# Tercera categoria: el guard que mas importa
# ---------------------------------------------------------------------------


class TestTerceraCategoria(unittest.TestCase):
    """Una cita puede probar lo contrario de lo que parece."""

    def test_tramite_provincial_no_es_fiscalizacion_municipal(self):
        cita = (
            "El Certificado de Aptitud Ambiental para establecimientos de "
            "tercera categoria es emitido por el OPDS."
        )
        self.assertIs(
            clasificar(cita, FISCALIZACION, TipoEvidencia.OFICIAL),
            Estado.NO_COMPETE,
        )

    def test_municipio_inspeccionando_si_confirma(self):
        cita = (
            "La Direccion de Medio Ambiente municipal realiza inspecciones "
            "periodicas a los establecimientos de tercera categoria radicados "
            "en el partido."
        )
        self.assertIs(
            clasificar(cita, FISCALIZACION, TipoEvidencia.OFICIAL),
            Estado.CONFIRMADO,
        )

    def test_convenio_con_la_provincia_confirma(self):
        """Nombra a OPDS, pero pone al municipio a fiscalizar."""
        cita = (
            "Por convenio con el OPDS, la Municipalidad asume la fiscalizacion "
            "de los establecimientos de segunda y tercera categoria."
        )
        self.assertIs(
            clasificar(cita, FISCALIZACION, TipoEvidencia.OFICIAL),
            Estado.CONFIRMADO,
        )

    def test_deteccion_de_organismo_ajeno(self):
        self.assertTrue(
            menciona_organismo_ajeno("tramite ante el OPDS provincial", FISCALIZACION)
        )
        self.assertFalse(
            menciona_organismo_ajeno("inspeccion de la direccion de ambiente", FISCALIZACION)
        )

    def test_un_subtema_sin_organismos_ajenos_no_se_ve_afectado(self):
        cita = "El OPDS acompano la jornada de promotores ambientales del municipio."
        # PROMOTORES no declara organismos ajenos: la regla no aplica.
        self.assertIs(
            clasificar(cita, PROMOTORES, TipoEvidencia.OFICIAL), Estado.CONFIRMADO
        )


# ---------------------------------------------------------------------------
# La prensa no confirma politica
# ---------------------------------------------------------------------------


class TestPrensaNoConfirma(unittest.TestCase):
    def test_prensa_es_indicio_aunque_la_cita_sea_buena(self):
        cita = "El municipio capacito a treinta promotores ambientales en el barrio Centro."
        self.assertIs(
            clasificar(cita, PROMOTORES, TipoEvidencia.PRENSA), Estado.INDICIO
        )

    def test_la_misma_cita_en_fuente_oficial_confirma(self):
        cita = "El municipio capacito a treinta promotores ambientales en el barrio Centro."
        self.assertIs(
            clasificar(cita, PROMOTORES, TipoEvidencia.OFICIAL), Estado.CONFIRMADO
        )

    def test_normativa_confirma(self):
        cita = "Ordenanza 4521: crease el programa municipal de promotores ambientales."
        self.assertIs(
            clasificar(cita, PROMOTORES, TipoEvidencia.NORMATIVA), Estado.CONFIRMADO
        )

    def test_prensa_que_prueba_que_no_compete_sigue_siendo_no_compete(self):
        """NO_COMPETE es una afirmacion sobre el mundo, no sobre la fuente."""
        cita = "Las plantas de tercera categoria son fiscalizadas por el OPDS."
        self.assertIs(
            clasificar(cita, FISCALIZACION, TipoEvidencia.PRENSA), Estado.NO_COMPETE
        )


# ---------------------------------------------------------------------------
# Un anuncio no es un hecho
# ---------------------------------------------------------------------------


class TestAnuncioNoEsHecho(unittest.TestCase):
    def test_obra_futura_no_confirma_accion(self):
        cita = "Se construira una planta de reciclado en el predio municipal."
        self.assertIs(
            clasificar(cita, ACCIONES, TipoEvidencia.OFICIAL), Estado.SIN_EVIDENCIA
        )

    def test_accion_en_curso_confirma(self):
        cita = "La planta de separacion en origen funciona de lunes a viernes."
        self.assertIs(
            clasificar(cita, ACCIONES, TipoEvidencia.OFICIAL), Estado.CONFIRMADO
        )

    def test_marca_de_hecho_gana_a_marca_de_futuro(self):
        cita = "La planta que se construira en 2019 hoy funciona todos los dias."
        self.assertFalse(es_anuncio_a_futuro(cita))

    def test_los_tres_subtemas_ambientales_exigen_hecho(self):
        """Las tres preguntas son sobre el presente, asi que un anuncio no vale."""
        cita = "Se implementara el programa de promotores ambientales en 2027."
        self.assertTrue(es_anuncio_a_futuro(cita))
        for sub in TEMA_AMBIENTAL.subtemas:
            self.assertTrue(sub.exige_hecho, sub.id)
        self.assertIs(
            clasificar(cita, PROMOTORES, TipoEvidencia.OFICIAL), Estado.SIN_EVIDENCIA
        )

    def test_el_guard_solo_aplica_donde_se_pidio(self):
        """Un sub-tema que no lo pide acepta el anuncio: la ordenanza ya es el hecho."""
        sin_exigencia = SubTema(
            id="ordenanza_ambiental",
            pregunta="Hay ordenanza ambiental?",
            que_prueba="La cita nombra la ordenanza.",
        )
        cita = "Se implementara lo dispuesto por la ordenanza ambiental 4521."
        self.assertTrue(es_anuncio_a_futuro(cita))
        self.assertIs(
            clasificar(cita, sin_exigencia, TipoEvidencia.OFICIAL), Estado.CONFIRMADO
        )


class TestCitaMinima(unittest.TestCase):
    def test_cita_corta_no_prueba_nada(self):
        self.assertIs(
            clasificar("ambiente", ACCIONES, TipoEvidencia.OFICIAL), Estado.SIN_EVIDENCIA
        )

    def test_cita_vacia(self):
        self.assertIs(
            clasificar("", ACCIONES, TipoEvidencia.OFICIAL), Estado.SIN_EVIDENCIA
        )


class TestConciliar(unittest.TestCase):
    """Cuando el modelo y el codigo discrepan, gana el mas conservador."""

    def test_el_modelo_no_puede_subir_el_estado(self):
        self.assertIs(conciliar("confirmado", Estado.INDICIO), Estado.INDICIO)

    def test_el_modelo_si_puede_bajarlo(self):
        self.assertIs(conciliar("no_compete", Estado.CONFIRMADO), Estado.NO_COMPETE)

    def test_estado_invalido_se_ignora(self):
        self.assertIs(conciliar("cualquier_cosa", Estado.CONFIRMADO), Estado.CONFIRMADO)

    def test_sin_propuesta_vale_el_codigo(self):
        self.assertIs(conciliar(None, Estado.CONFIRMADO), Estado.CONFIRMADO)


# ---------------------------------------------------------------------------
# Verificacion de la respuesta del modelo (ADR-0014)
# ---------------------------------------------------------------------------


class TestVerificacion(unittest.TestCase):
    def setUp(self):
        self.texto = (
            "La Municipalidad cuenta con un programa de promotores ambientales "
            "que recorre los barrios. La planta de separacion en origen funciona "
            "de lunes a viernes de 7 a 13."
        )
        self.paginas = [pagina(self.texto)]

    def _verificar(self, hallazgos):
        return verificar_respuesta(
            {"hallazgos": hallazgos},
            municipio="Navarro",
            id_municipio="MUN-BA-001",
            tema=TEMA_AMBIENTAL,
            paginas=self.paginas,
            fecha="2026-08-15",
        )

    def test_cita_literal_pasa(self):
        r = self._verificar([{
            "subtema": "promotores_ambientales",
            "resumen": "Hay programa de promotores.",
            "cita_literal": "programa de promotores ambientales que recorre los barrios",
            "pagina": 1,
        }])
        self.assertEqual(len(r), 1)
        self.assertIs(r[0].estado, Estado.CONFIRMADO)
        self.assertEqual(r[0].url, "https://x.gob.ar/")

    def test_cita_inventada_se_descarta(self):
        r = self._verificar([{
            "subtema": "promotores_ambientales",
            "resumen": "Dice que hay 40 promotores.",
            "cita_literal": "el municipio capacito a 40 promotores ambientales",
            "pagina": 1,
        }])
        self.assertEqual(r, [])

    def test_subtema_inexistente_se_descarta(self):
        r = self._verificar([{
            "subtema": "arbolado",
            "resumen": "x",
            "cita_literal": "programa de promotores ambientales",
            "pagina": 1,
        }])
        self.assertEqual(r, [])

    def test_indice_de_pagina_equivocado_no_rompe(self):
        """El indice es lo primero que alucina: se prueba contra todas."""
        r = self._verificar([{
            "subtema": "promotores_ambientales",
            "resumen": "x",
            "cita_literal": "programa de promotores ambientales que recorre los barrios",
            "pagina": 99,
        }])
        self.assertEqual(len(r), 1)

    def test_respuesta_vacia_o_rota(self):
        for entrada in (None, {}, {"hallazgos": None}, {"hallazgos": "texto"}):
            self.assertEqual(
                verificar_respuesta(
                    entrada, municipio="N", id_municipio="M", tema=TEMA_AMBIENTAL,
                    paginas=self.paginas, fecha="2026-08-15",
                ),
                [],
            )

    def test_el_tipo_de_evidencia_viaja_desde_la_pagina(self):
        self.paginas = [pagina(self.texto, tipo="prensa", evidencia=TipoEvidencia.PRENSA)]
        r = self._verificar([{
            "subtema": "promotores_ambientales",
            "resumen": "x",
            "cita_literal": "programa de promotores ambientales que recorre los barrios",
            "pagina": 1,
        }])
        self.assertIs(r[0].estado, Estado.INDICIO)
        self.assertIs(r[0].tipo_evidencia, TipoEvidencia.PRENSA)

    def test_techo_por_subtema(self):
        from interrogador import MAX_POR_SUBTEMA

        crudo = {
            "subtema": "promotores_ambientales",
            "resumen": "x",
            "cita_literal": "programa de promotores ambientales que recorre los barrios",
            "pagina": 1,
        }
        r = self._verificar([dict(crudo) for _ in range(MAX_POR_SUBTEMA + 5)])
        self.assertEqual(len(r), MAX_POR_SUBTEMA)


# ---------------------------------------------------------------------------
# Cosecha de enlaces
# ---------------------------------------------------------------------------


class TestCosechaDeEnlaces(unittest.TestCase):
    HTML = """
    <a href="/medio-ambiente/puntos-verdes">Puntos verdes</a>
    <a href="/turnos">Turnos de salud</a>
    <a href="/tasas">Tasas municipales</a>
    <a href="https://opds.gba.gob.ar/tramite">Aptitud ambiental (Provincia)</a>
    <a href="/compostaje">Compostaje domiciliario</a>
    """

    def test_sigue_los_enlaces_del_tema(self):
        urls = [
            c.url
            for c in enlaces_del_tema(self.HTML, "https://x.gob.ar/", TEMA_AMBIENTAL)
        ]
        self.assertIn("https://x.gob.ar/medio-ambiente/puntos-verdes", urls)
        self.assertIn("https://x.gob.ar/compostaje", urls)

    def test_ignora_los_ajenos_al_tema(self):
        urls = [
            c.url
            for c in enlaces_del_tema(self.HTML, "https://x.gob.ar/", TEMA_AMBIENTAL)
        ]
        self.assertNotIn("https://x.gob.ar/turnos", urls)
        self.assertNotIn("https://x.gob.ar/tasas", urls)

    def test_no_sale_del_host(self):
        """Que el municipio linkee a OPDS no convierte a OPDS en fuente municipal."""
        urls = [
            c.url
            for c in enlaces_del_tema(self.HTML, "https://x.gob.ar/", TEMA_AMBIENTAL)
        ]
        self.assertFalse(any("opds.gba.gob.ar" in u for u in urls))

    def test_no_repite_lo_ya_leido(self):
        urls = [
            c.url
            for c in enlaces_del_tema(
                self.HTML, "https://x.gob.ar/", TEMA_AMBIENTAL,
                ya_leidas=["https://x.gob.ar/compostaje"],
            )
        ]
        self.assertNotIn("https://x.gob.ar/compostaje", urls)


# ---------------------------------------------------------------------------
# Agregacion por municipio
# ---------------------------------------------------------------------------


class TestFragmentosRelevantes(unittest.TestCase):
    """El corte a 4000 por el principio dejaba la caratula del boletin.

    Es la segunda mitad del bug que dejo promotores y fiscalizacion en cero:
    un boletin de SIBOM son 320.000 caracteres y la ordenanza ambiental esta en
    la pagina 60.
    """

    def test_texto_corto_pasa_entero(self):
        t = "La Municipalidad tiene promotores ambientales."
        self.assertEqual(fragmentos_relevantes(t, TEMA_AMBIENTAL.senales), t)

    def test_encuentra_la_ordenanza_enterrada(self):
        relleno = "Visto el expediente y considerando lo actuado. " * 8000
        ordenanza = "ORDENANZA 4521: crease el programa de promotores ambientales."
        boletin = relleno + ordenanza + relleno

        self.assertGreater(len(boletin), 300_000)
        frag = fragmentos_relevantes(boletin, TEMA_AMBIENTAL.senales)

        self.assertIn("promotores ambientales", frag)
        self.assertIn("ORDENANZA 4521", frag)
        self.assertLessEqual(len(frag), 4200)

    def test_el_corte_viejo_no_la_encontraba(self):
        """Deja constancia de por que fallaba, para que no vuelva."""
        relleno = "Visto el expediente y considerando lo actuado. " * 8000
        boletin = relleno + "ORDENANZA 4521: promotores ambientales." + relleno
        self.assertNotIn("promotores ambientales", boletin[:4000])

    def test_sin_senales_cae_al_principio(self):
        t = "Nada del tema. " * 1000
        frag = fragmentos_relevantes(t, TEMA_AMBIENTAL.senales)
        self.assertEqual(frag, t[:4000])

    def test_respeta_el_tope(self):
        t = ("hay un punto verde aca. " + "x" * 3000) * 40
        self.assertLessEqual(len(fragmentos_relevantes(t, TEMA_AMBIENTAL.senales)), 4200)

    def test_tolera_tildes_en_el_texto(self):
        """Las senales van sin tilde; el boletin las trae con tilde."""
        relleno = "z" * 5000
        t = relleno + "programa de separación en origen vigente" + relleno
        frag = fragmentos_relevantes(t, TEMA_AMBIENTAL.senales)
        self.assertIn("separación en origen", frag)

    def test_ventanas_solapadas_no_duplican(self):
        relleno = "y" * 5000
        t = relleno + "punto verde y compostaje juntos" + relleno
        frag = fragmentos_relevantes(t, TEMA_AMBIENTAL.senales)
        self.assertEqual(frag.count("punto verde y compostaje juntos"), 1)


class TestBoletines(unittest.TestCase):
    """SIBOM se lee con el lector de gabinete, no bajando el indice."""

    def test_usa_el_lector_y_marca_normativa(self):
        class BoletinFalso:
            url = "https://sibom.slyt.gba.gob.ar/bulletins/117"
            texto = (
                "VISTO el expediente 4521/21 y CONSIDERANDO que resulta necesario "
                "fortalecer la gestion ambiental del partido, el Honorable Concejo "
                "Deliberante sanciona con fuerza de ORDENANZA: crease el programa "
                "municipal de promotores ambientales."
            )

        paginas = boletines_del_municipio(
            "Chascomus", TEMA_AMBIENTAL, lector=lambda m, n: [BoletinFalso()]
        )
        self.assertEqual(len(paginas), 1)
        self.assertIs(paginas[0].tipo_evidencia, TipoEvidencia.NORMATIVA)
        self.assertIn("promotores ambientales", paginas[0].texto)

    def test_municipio_que_nunca_publico(self):
        """21 de los 86 estan en SIBOM pero no publicaron. No es un error."""
        self.assertEqual(
            boletines_del_municipio("Navarro", TEMA_AMBIENTAL, lector=lambda m, n: []),
            [],
        )

    def test_boletin_vacio_se_descarta(self):
        class Vacio:
            url = "u"
            texto = "corto"

        self.assertEqual(
            boletines_del_municipio("X", TEMA_AMBIENTAL, lector=lambda m, n: [Vacio()]),
            [],
        )

    def test_recorta_el_boletin_por_senales(self):
        class Largo:
            url = "u"
            texto = "a" * 200_000 + "los puntos verdes funcionan" + "b" * 200_000

        p = boletines_del_municipio("X", TEMA_AMBIENTAL, lector=lambda m, n: [Largo()])[0]
        self.assertIn("los puntos verdes funcionan", p.texto)
        self.assertLess(len(p.texto), 5000)


class TestEstadoPorSubtema(unittest.TestCase):
    def _h(self, estado, subtema="acciones_ambientales"):
        return HallazgoTema(
            municipio="N", id_municipio="M", tema="ambiental", subtema=subtema,
            estado=estado, cita="x" * 20, url="u", tipo_evidencia=TipoEvidencia.OFICIAL,
            fecha="2026-08-15",
        )

    def test_confirmado_gana_a_indicio(self):
        m = MunicipioTema(
            municipio="N", id_municipio="M", tema="ambiental",
            hallazgos=[self._h(Estado.INDICIO), self._h(Estado.CONFIRMADO)],
        )
        self.assertIs(m.estado_de("acciones_ambientales"), Estado.CONFIRMADO)

    def test_indicio_gana_a_no_compete(self):
        m = MunicipioTema(
            municipio="N", id_municipio="M", tema="ambiental",
            hallazgos=[self._h(Estado.NO_COMPETE), self._h(Estado.INDICIO)],
        )
        self.assertIs(m.estado_de("acciones_ambientales"), Estado.INDICIO)

    def test_sin_hallazgos_es_sin_evidencia(self):
        m = MunicipioTema(municipio="N", id_municipio="M", tema="ambiental")
        self.assertIs(m.estado_de("acciones_ambientales"), Estado.SIN_EVIDENCIA)


# ---------------------------------------------------------------------------
# El tema es configuracion
# ---------------------------------------------------------------------------


class TestTemaEsConfiguracion(unittest.TestCase):
    def test_un_tema_nuevo_no_necesita_codigo(self):
        """Se declara un tema inventado y los guards funcionan igual."""
        nuevo = SubTema(
            id="bacheo",
            pregunta="El municipio tiene plan de bacheo?",
            que_prueba="La cita muestra al municipio bacheando.",
            senales=("bacheo", "repavimentacion"),
            exige_hecho=True,
        )
        self.assertIs(
            clasificar("El plan de bacheo se realiza todos los meses.", nuevo,
                       TipoEvidencia.OFICIAL),
            Estado.CONFIRMADO,
        )
        self.assertIs(
            clasificar("Se implementara un plan de bacheo.", nuevo,
                       TipoEvidencia.OFICIAL),
            Estado.SIN_EVIDENCIA,
        )

    def test_el_tema_ambiental_esta_registrado(self):
        self.assertIn("ambiental", ids_temas())
        self.assertIs(tema("ambiental"), TEMA_AMBIENTAL)

    def test_tema_inexistente_dice_cuales_hay(self):
        with self.assertRaises(KeyError) as ctx:
            tema("inexistente")
        self.assertIn("ambiental", str(ctx.exception))

    def test_los_tres_subtemas_pedidos(self):
        self.assertEqual(
            TEMA_AMBIENTAL.ids_subtemas,
            ("promotores_ambientales", "fiscalizacion_3ra", "acciones_ambientales"),
        )


class TestMarcasMunicipales(unittest.TestCase):
    def test_reconoce_al_municipio_como_sujeto(self):
        for cita in (
            "La Municipalidad de Navarro inspecciona",
            "El municipio realiza",
            "Ordenanza 1234 del Concejo Deliberante",
            "La Direccion de Medio Ambiente controla",
        ):
            self.assertTrue(menciona_al_municipio(cita), cita)

    def test_no_confunde_texto_provincial(self):
        self.assertFalse(
            menciona_al_municipio("El OPDS emite el certificado correspondiente.")
        )


if __name__ == "__main__":
    unittest.main()
