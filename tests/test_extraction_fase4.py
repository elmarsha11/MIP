"""
Tests Fase 4 - Extraccion verificada.

No usan red ni consumen cuota de Gemini: el cliente se reemplaza por
ClienteFalso. Lo que se prueba es la regla de ADR-0014: la IA propone, el
codigo verifica, y una cita inventada no puede entrar a la base.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "extraction"))
sys.path.insert(1, str(PROJECT_ROOT / "src" / "discovery"))

from pydantic import ValidationError  # noqa: E402

from extractor import (  # noqa: E402
    ESQUEMA_RESPUESTA,
    construir_prompt,
    extraer,
    hallazgos_deterministicos,
    verificar_respuesta,
)
from fetcher import Pagina, URLTipificada, limpiar_html  # noqa: E402
from gemini_client import ClienteFalso, CuotaAgotada, LimitadorCuota  # noqa: E402
import extraction_engine as engine  # noqa: E402
from modelos import (  # noqa: E402
    DOMINIO_VALORES,
    Confianza,
    EstadoHallazgo,
    Hallazgo,
    TipoFuente,
    Valor,
    Variable,
    cita_esta_en_fuente,
)
from modelos import MunicipioExtraccion  # noqa: E402

FECHA = "2026-08-07T12:00:00Z"

TEXTO = (
    "Municipalidad de Navarro. Tramites y Servicios: Habilitacion de Comercios, "
    "Licencia de Conducir. Solicita tu turno medico online en el CAPS a traves "
    "del formulario web. Boletin Oficial disponible."
)

PAGINA = Pagina(
    url="https://navarro.gob.ar/tramites-y-servicios/",
    tipo="tramites",
    confianza_url="Alta",
    texto=TEXTO,
)


def respuesta(variable, valor, cita, pagina=1, detalle=""):
    return {
        "_modelo": "gemini-test",
        "hallazgos": [
            {
                "variable": variable.value,
                "valor": valor,
                "cita_literal": cita,
                "pagina": pagina,
                "detalle": detalle,
            }
        ],
    }


class TestVerificacionDeCitas(unittest.TestCase):
    def test_cita_literal_se_encuentra(self):
        self.assertTrue(cita_esta_en_fuente("Habilitacion de Comercios", TEXTO))

    def test_tolera_espaciado_y_mayusculas(self):
        self.assertTrue(cita_esta_en_fuente("HABILITACION   DE  COMERCIOS", TEXTO))

    def test_tolera_comillas_tipograficas(self):
        fuente = 'El municipio dice "turno medico online" en su portal'
        self.assertTrue(cita_esta_en_fuente("“turno medico online”", fuente))

    def test_parafrasis_no_pasa(self):
        """El limite entre citar y parafrasear: palabras distintas no valen."""
        self.assertFalse(cita_esta_en_fuente("Habilitaciones Comerciales", TEXTO))

    def test_cita_muy_corta_no_prueba_nada(self):
        self.assertFalse(cita_esta_en_fuente("turno", TEXTO))

    def test_cita_inventada_no_pasa(self):
        self.assertFalse(
            cita_esta_en_fuente("El municipio cuenta con expediente digital GDE", TEXTO)
        )


class TestADR0014(unittest.TestCase):
    """Una alucinacion no puede sobrevivir al pipeline."""

    def _verificar(self, resp):
        return verificar_respuesta(resp, "Navarro", "MUN-BA-004", [PAGINA], FECHA)

    def test_cita_real_produce_hallazgo_verificado(self):
        h = {x.variable: x for x in self._verificar(
            respuesta(Variable.TURNOS_SALUD_ONLINE, "si", "Solicita tu turno medico online en el CAPS")
        )}[Variable.TURNOS_SALUD_ONLINE]
        self.assertIs(h.estado, EstadoHallazgo.VERIFICADO)
        self.assertEqual(h.valor, "si")
        self.assertEqual(h.url, PAGINA.url)
        self.assertIs(h.confianza, Confianza.ALTA)
        self.assertEqual(h.modelo, "gemini-test")

    def test_cita_inventada_se_rechaza_y_no_deja_dato(self):
        h = {x.variable: x for x in self._verificar(
            respuesta(Variable.EXPEDIENTE_DIGITAL_GDE, "si", "El municipio implemento el sistema GDE en 2024")
        )}[Variable.EXPEDIENTE_DIGITAL_GDE]
        self.assertIs(h.estado, EstadoHallazgo.CITA_RECHAZADA)
        self.assertEqual(h.valor, Valor.NO_VERIFICABLE.value)
        self.assertIsNone(h.fragmento)
        self.assertIs(h.confianza, Confianza.CERO)

    def test_numero_de_pagina_equivocado_no_invalida_una_cita_real(self):
        """Confundirse de pagina es un desliz; inventar la cita no."""
        h = {x.variable: x for x in self._verificar(
            respuesta(Variable.TRAMITES_ONLINE, "si", "Habilitacion de Comercios", pagina=7)
        )}[Variable.TRAMITES_ONLINE]
        self.assertIs(h.estado, EstadoHallazgo.VERIFICADO)

    def test_no_verificable_es_respuesta_valida(self):
        h = {x.variable: x for x in self._verificar(
            respuesta(Variable.SISTEMA_RAFAM, "no_verificable", "")
        )}[Variable.SISTEMA_RAFAM]
        self.assertIs(h.estado, EstadoHallazgo.NO_VERIFICABLE)

    def test_todas_las_variables_aparecen_aunque_el_modelo_las_omita(self):
        """ADR-0009: el vacio se ve, no desaparece."""
        hallazgos = self._verificar(respuesta(Variable.TRAMITES_ONLINE, "si", "Habilitacion de Comercios"))
        self.assertEqual(len(hallazgos), len(Variable))

    def test_ia_sin_respuesta_no_inventa_nada(self):
        hallazgos = self._verificar(None)
        self.assertEqual(len(hallazgos), len(Variable))
        self.assertTrue(all(h.valor == Valor.NO_VERIFICABLE.value for h in hallazgos))


class TestModeloHallazgo(unittest.TestCase):
    def _base(self, **kw):
        datos = dict(
            municipio="Navarro", id_municipio="MUN-BA-004",
            variable=Variable.TRAMITES_ONLINE, valor="si",
            url="https://navarro.gob.ar/", fecha=FECHA,
            fragmento="Tramites y Servicios", tipo_fuente=TipoFuente.PORTAL_OFICIAL,
            confianza=Confianza.ALTA, estado=EstadoHallazgo.VERIFICADO,
        )
        datos.update(kw)
        return datos

    def test_verificado_sin_fragmento_falla(self):
        with self.assertRaises(ValidationError) as ctx:
            Hallazgo(**self._base(fragmento=None))
        self.assertIn("ADR-0014", str(ctx.exception))

    def test_verificado_sin_url_falla(self):
        with self.assertRaises(ValidationError):
            Hallazgo(**self._base(url=None))

    def test_no_verificado_no_puede_afirmar_si(self):
        with self.assertRaises(ValidationError) as ctx:
            Hallazgo(**self._base(estado=EstadoHallazgo.NO_VERIFICABLE, valor="si"))
        self.assertIn("ADR-0009", str(ctx.exception))

    def test_no_verificado_no_puede_tener_confianza_alta(self):
        with self.assertRaises(ValidationError):
            Hallazgo(
                **self._base(
                    estado=EstadoHallazgo.CITA_RECHAZADA,
                    valor=Valor.NO_VERIFICABLE.value,
                    confianza=Confianza.ALTA,
                    fragmento=None,
                    url=None,
                )
            )

    def test_id_estable_por_municipio_y_variable(self):
        a = Hallazgo(**self._base())
        b = Hallazgo(**self._base(fragmento="Otro fragmento"))
        self.assertEqual(a.id, b.id)  # misma variable, mismo municipio


class TestCapaDeterministica(unittest.TestCase):
    """Lo que Fase 3 ya probo no se le pregunta a la IA."""

    def test_url_de_licitaciones_prueba_la_variable(self):
        urls = [URLTipificada("https://navarro.gob.ar/licitaciones/", "licitaciones", "Alta",
                              "Licitaciones - Navarro Municipalidad")]
        h = hallazgos_deterministicos(urls, "Navarro", "MUN-BA-004", FECHA)
        self.assertIn(Variable.LICITACIONES, h)
        self.assertEqual(h[Variable.LICITACIONES].valor, "si")
        self.assertIsNone(h[Variable.LICITACIONES].modelo)  # sin IA

    def test_sin_fragmento_no_hay_dato(self):
        urls = [URLTipificada("https://x/licitaciones/", "licitaciones", "Alta", None)]
        self.assertEqual(hallazgos_deterministicos(urls, "X", "MUN-BA-001", FECHA), {})

    def test_pagina_de_salud_no_prueba_turnos_online(self):
        """El caso testigo del diccionario: tener seccion de salud no es tener turnero."""
        urls = [URLTipificada("https://x/salud/", "salud_turnos", "Alta", "Salud - Municipalidad")]
        h = hallazgos_deterministicos(urls, "X", "MUN-BA-001", FECHA)
        self.assertNotIn(Variable.TURNOS_SALUD_ONLINE, h)

    def test_no_se_le_pregunta_a_la_ia_lo_ya_probado(self):
        urls = [URLTipificada("https://x/licitaciones/", "licitaciones", "Alta", "Licitaciones")]
        cliente = ClienteFalso([respuesta(Variable.TRAMITES_ONLINE, "si", "Habilitacion de Comercios")])
        extraer("Navarro", "MUN-BA-004", [PAGINA], cliente, FECHA, urls)
        self.assertNotIn("licitaciones (valores:", cliente.prompts[0])


class TestPrompt(unittest.TestCase):
    def test_incluye_las_paginas_numeradas_con_su_url(self):
        p = construir_prompt("Navarro", [PAGINA])
        self.assertIn("--- PAGINA 1", p)
        self.assertIn(PAGINA.url, p)
        self.assertIn(TEXTO[:40], p)

    def test_pide_explicitamente_admitir_el_vacio(self):
        p = construir_prompt("Navarro", [PAGINA])
        self.assertIn("no_verificable", p)
        self.assertIn("No infieras", p)

    def test_solo_pregunta_las_variables_pedidas(self):
        p = construir_prompt("Navarro", [PAGINA], [Variable.TURNOS_SALUD_ONLINE])
        self.assertIn("turnos_salud_online (valores:", p)
        self.assertNotIn("licitaciones (valores:", p)

    def test_el_prompt_declara_los_valores_admitidos(self):
        """El esquema ya no fija un enum unico: cada variable tiene su dominio,
        asi que los valores admitidos se declaran en el prompt."""
        campos = ESQUEMA_RESPUESTA["properties"]["hallazgos"]["items"]["properties"]
        self.assertNotIn("enum", campos["valor"])
        p = construir_prompt("Navarro", [PAGINA], [Variable.CANAL_TURNOS_SALUD])
        self.assertIn("valores: web/whatsapp/telegram", p)
        self.assertIn("no_verificable", p)

    def test_el_prompt_marca_las_variables_de_texto_libre(self):
        p = construir_prompt("Chascomus", [PAGINA], [Variable.INTENDENTE])
        self.assertIn("texto libre", p)


class TestCanalDeTurnos(unittest.TestCase):
    """El canal es lo que vuelve comparables municipios incomparables: un
    formulario web, un bot de WhatsApp y una fila a las 5 AM no son lo mismo."""

    def test_canal_admite_whatsapp_y_telegram(self):
        for canal in ("web", "whatsapp", "telegram", "app", "telefono", "presencial"):
            with self.subTest(canal=canal):
                self.assertIn(canal, DOMINIO_VALORES[Variable.CANAL_TURNOS_SALUD])

    def test_variables_binarias_no_admiten_canales(self):
        self.assertNotIn("whatsapp", DOMINIO_VALORES[Variable.TURNOS_SALUD_ONLINE])

    def test_valor_fuera_del_dominio_no_entra(self):
        with self.assertRaises(ValidationError):
            Hallazgo(
                municipio="X", id_municipio="MUN-BA-001",
                variable=Variable.TURNOS_SALUD_ONLINE, valor="parcial",
                url="https://x.gob.ar/", fecha=FECHA, fragmento="Turnos parciales",
                confianza=Confianza.ALTA, estado=EstadoHallazgo.VERIFICADO,
            )

    def test_el_modelo_inventa_un_valor_y_queda_sin_dato(self):
        h = {x.variable: x for x in verificar_respuesta(
            respuesta(Variable.CANAL_TURNOS_SALUD, "carta_documento", "Solicita tu turno medico online"),
            "Navarro", "MUN-BA-004", [PAGINA], FECHA,
        )}[Variable.CANAL_TURNOS_SALUD]
        self.assertIs(h.estado, EstadoHallazgo.NO_VERIFICABLE)

    def test_canal_presencial_es_un_hallazgo_no_un_vacio(self):
        """Pinamar: 'acercarse a la mesa de admision' es una ausencia probada,
        y es justamente el municipio al que hay que venderle."""
        pagina = Pagina(
            url="https://pinamar.gob.ar/salud/", tipo="salud_turnos", confianza_url="Alta",
            texto="Para obtener el turno acercarse a la mesa de admision del Centro de Salud.",
        )
        h = {x.variable: x for x in verificar_respuesta(
            respuesta(Variable.CANAL_TURNOS_SALUD, "presencial",
                      "acercarse a la mesa de admision del Centro de Salud"),
            "Pinamar", "MUN-BA-001", [pagina], FECHA,
        )}[Variable.CANAL_TURNOS_SALUD]
        self.assertIs(h.estado, EstadoHallazgo.VERIFICADO)
        self.assertEqual(h.valor, "presencial")


class TestTildes(unittest.TestCase):
    """Los portales municipales sirven mal la codificacion y el modelo cita
    bien. Sin tolerar tildes se descartaban citas correctas."""

    def test_cita_sin_tildes_coincide_con_fuente_acentuada(self):
        self.assertTrue(
            cita_esta_en_fuente("BOLETIN OFICIAL MUNICIPAL", "Acceda al Boletín Oficial Municipal")
        )

    def test_sigue_sin_tolerar_palabras_distintas(self):
        self.assertFalse(
            cita_esta_en_fuente("Boletines Oficiales Municipales", "Acceda al Boletín Oficial Municipal")
        )


class TestNoDestruirEvidencia(unittest.TestCase):
    """ADR-0013 aplicado a Fase 4: un dato verificado no se pisa con un vacio.

    El modelo no es determinista: el mismo municipio dio 'si' con cita en una
    corrida y 'no_verificable' en la siguiente. Sin esta regla, re-correr
    borraba evidencia ya probada."""

    def _guardar(self, db, valor, estado, fragmento, url):
        r = MunicipioExtraccion(
            municipio="Arrecifes", id_municipio="MUN-BA-010", fecha=FECHA,
            hallazgos=[Hallazgo(
                municipio="Arrecifes", id_municipio="MUN-BA-010",
                variable=Variable.TURNOS_SALUD_ONLINE, valor=valor, url=url,
                fecha=FECHA, fragmento=fragmento, confianza=(
                    Confianza.ALTA if estado is EstadoHallazgo.VERIFICADO else Confianza.CERO),
                estado=estado,
            )],
        )
        engine.guardar_sqlite([r], db)

    def test_una_corrida_peor_no_borra_la_evidencia(self):
        import tempfile, sqlite3 as sq
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "h.sqlite"
            self._guardar(db, "si", EstadoHallazgo.VERIFICADO, "HOSPITAL - TURNOS WEB",
                          "https://arrecifes.gob.ar/")
            self._guardar(db, "no_verificable", EstadoHallazgo.NO_VERIFICABLE, None, None)
            con = sq.connect(db)
            valor, estado, frag = con.execute(
                "select valor, estado, fragmento from hallazgos").fetchone()
            con.close()
            self.assertEqual(valor, "si")
            self.assertEqual(estado, "verificado")
            self.assertEqual(frag, "HOSPITAL - TURNOS WEB")

    def test_evidencia_nueva_si_reemplaza_a_la_vieja(self):
        import tempfile, sqlite3 as sq
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "h.sqlite"
            self._guardar(db, "si", EstadoHallazgo.VERIFICADO, "cita vieja verificada",
                          "https://a.gob.ar/")
            self._guardar(db, "no", EstadoHallazgo.VERIFICADO, "cita nueva verificada",
                          "https://a.gob.ar/nueva")
            con = sq.connect(db)
            valor, frag = con.execute("select valor, fragmento from hallazgos").fetchone()
            con.close()
            self.assertEqual(valor, "no")
            self.assertEqual(frag, "cita nueva verificada")


class TestVariablesDeTextoLibre(unittest.TestCase):
    """En una variable binaria el valor esta acotado a si/no y la cita solo lo
    respalda. En una de texto libre el VALOR ES EL DATO: si nadie comprueba que
    el nombre aparezca en la fuente, el modelo puede citar una frase real y
    colgarle cualquier nombre."""

    PAGINA_OBRAS = Pagina(
        url="https://chascomus.gob.ar/",
        tipo="sitio_oficial",
        confianza_url="Alta",
        texto=("El intendente Javier Gaston recorrio las obras de bacheo en el "
               "barrio Belgrano junto al secretario de Obras."),
    )

    def _verificar(self, valor, cita):
        return {x.variable: x for x in verificar_respuesta(
            respuesta(Variable.INTENDENTE, valor, cita),
            "Chascomus", "MUN-BA-011", [self.PAGINA_OBRAS], FECHA,
        )}[Variable.INTENDENTE]

    def test_nombre_inventado_con_cita_real_no_entra(self):
        """El caso que estaba abierto: cita verdadera, nombre falso."""
        h = self._verificar("Juan Perez", "recorrio las obras de bacheo en el barrio Belgrano")
        self.assertIs(h.estado, EstadoHallazgo.CITA_RECHAZADA)
        self.assertEqual(h.valor, Valor.NO_VERIFICABLE.value)

    def test_nombre_que_esta_en_la_cita_si_entra(self):
        h = self._verificar("Javier Gaston", "El intendente Javier Gaston recorrio las obras")
        self.assertIs(h.estado, EstadoHallazgo.VERIFICADO)
        self.assertEqual(h.valor, "Javier Gaston")

    def test_tolera_tildes_y_mayusculas_en_el_valor(self):
        h = self._verificar("JAVIER GASTÓN", "El intendente Javier Gaston recorrio las obras")
        self.assertIs(h.estado, EstadoHallazgo.VERIFICADO)

    def test_las_binarias_no_exigen_que_el_valor_este_en_la_cita(self):
        """'si' no aparece literal en ninguna cita, y no tiene por que."""
        h = {x.variable: x for x in verificar_respuesta(
            respuesta(Variable.TRAMITES_ONLINE, "si", "Habilitacion de Comercios"),
            "Navarro", "MUN-BA-004", [PAGINA], FECHA,
        )}[Variable.TRAMITES_ONLINE]
        self.assertIs(h.estado, EstadoHallazgo.VERIFICADO)

    def test_texto_libre_admite_cualquier_valor_del_dominio(self):
        self.assertIsNone(DOMINIO_VALORES[Variable.INTENDENTE])
        self.assertIsNotNone(DOMINIO_VALORES[Variable.TRAMITES_ONLINE])


class TestCuota(unittest.TestCase):
    def test_corta_al_llegar_al_tope_diario(self):
        limitador = LimitadorCuota(rpm_max=100, rpd_max=2)
        limitador._usadas = 0
        limitador.esperar_turno()
        limitador.esperar_turno()
        with self.assertRaises(CuotaAgotada):
            limitador.esperar_turno()

    def test_informa_cuantas_quedan(self):
        limitador = LimitadorCuota(rpm_max=100, rpd_max=10)
        limitador._usadas = 3
        self.assertEqual(limitador.restantes_hoy(), 7)


class TestLimpiezaHtml(unittest.TestCase):
    def test_saca_scripts_y_estilos(self):
        html = "<html><script>var x=1</script><style>a{}</style><p>Hola   mundo</p></html>"
        self.assertEqual(limpiar_html(html), "Hola mundo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
