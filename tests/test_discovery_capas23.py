"""
Tests Capa 2 (fuentes) y Capa 3 (validacion) - Fase 3.

No salen a la red: usan ProveedorFijo y HTML de ejemplo. Los tests que si
necesitan internet estan en test_discovery_integracion.py.

Correr:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "discovery"))

import discovery_engine as engine  # noqa: E402
import storage  # noqa: E402
from schemas import (  # noqa: E402
    MAX_URLS_POR_MUNICIPIO,
    Confianza,
    DiscoveryURL,
    EstadoValidacion,
    MunicipioDiscovery,
    TipoURL,
)
from search_provider import (  # noqa: E402
    PLANTILLAS_QUERY,
    ProveedorFijo,
    ResultadoBusqueda,
    buscar_urls,
    clasificar_tipo,
    construir_queries,
    es_dominio_oficial,
    parece_del_municipio,
)
from site_crawler import (  # noqa: E402
    candidatos_dominio,
    provincia_ajena,
    variantes_slug,
)
from validator import (  # noqa: E402
    calcular_confianza,
    extraer_titulo,
    titulo_es_del_municipio,
    url_apunta_al_municipio,
)


def candidata(**kwargs) -> DiscoveryURL:
    datos = dict(
        municipio="Navarro",
        id_municipio="MUN-BA-004",
        url="https://navarro.gob.ar/tramites/",
        tipo=TipoURL.TRAMITES,
        fuente_query="test",
        titulo_fragmento="Tramites – Navarro Municipalidad",
        confianza=Confianza.MEDIA,
        estado_validacion=EstadoValidacion.PENDIENTE,
        es_oficial=True,
    )
    datos.update(kwargs)
    return DiscoveryURL(**datos)


class TestClasificacionDeTipo(unittest.TestCase):
    def test_home_de_dominio_oficial_es_sitio_oficial(self):
        self.assertIs(clasificar_tipo("https://navarro.gob.ar/"), TipoURL.SITIO_OFICIAL)
        self.assertIs(clasificar_tipo("https://tresarroyos.gov.ar/"), TipoURL.SITIO_OFICIAL)

    def test_home_de_dominio_no_oficial_no_es_sitio_oficial(self):
        self.assertIs(clasificar_tipo("https://ejemplo.com/"), TipoURL.OTRO)

    def test_secciones_conocidas(self):
        casos = {
            "https://x.gob.ar/tramites-y-servicios/": TipoURL.TRAMITES,
            "https://x.gob.ar/transparencia/": TipoURL.TRANSPARENCIA,
            "https://x.gob.ar/boletin-oficial": TipoURL.BOLETIN_SIBOM,
            "https://x.gob.ar/turnos/": TipoURL.SALUD_TURNOS,
            "https://x.gob.ar/tasas/": TipoURL.HACIENDA_TASAS_RAFAM,
            "https://x.gob.ar/reclamos/": TipoURL.RECLAMOS_147,
            "https://x.gob.ar/ordenanzas/": TipoURL.NORMATIVA_ORDENANZAS,
            "https://x.gob.ar/licitaciones/": TipoURL.LICITACIONES,
            "https://x.gob.ar/mesa-de-entradas/": TipoURL.GDE_EXPEDIENTE,
        }
        for url, esperado in casos.items():
            with self.subTest(url=url):
                self.assertIs(clasificar_tipo(url), esperado)

    def test_redes_y_stores_por_dominio(self):
        self.assertIs(
            clasificar_tipo("https://www.facebook.com/municipionavarro/"),
            TipoURL.FACEBOOK_OFICIAL,
        )
        self.assertIs(
            clasificar_tipo("https://play.google.com/store/apps/details?id=ar.mi.app"),
            TipoURL.PLAY_STORE,
        )

    def test_nota_de_prensa_no_se_confunde_con_seccion(self):
        """Un WordPress redirige /salud/ a la nota mas parecida. No es la seccion."""
        nota = "https://navarro.gob.ar/salud-para-todos-mas-de-380-vecinas-y-vecinos-atendidos-en-el-caps/"
        self.assertIs(clasificar_tipo(nota), TipoURL.OTRO)
        self.assertIs(clasificar_tipo("https://x.gob.ar/noticia/turnos-de-salud"), TipoURL.OTRO)
        # pero una seccion con guiones normales si se reconoce
        self.assertIs(clasificar_tipo("https://x.gob.ar/tramites-y-servicios/"), TipoURL.TRAMITES)


class TestPertinencia(unittest.TestCase):
    def test_dominio_oficial_ajeno_no_alcanza(self):
        """arba.gov.ar y el SIBOM provincial son oficiales y no son del municipio."""
        self.assertTrue(es_dominio_oficial("https://www.arba.gov.ar/"))
        self.assertFalse(parece_del_municipio("https://www.arba.gov.ar/", "Navarro", "ARBA"))

    def test_url_con_el_nombre_del_municipio_pasa(self):
        self.assertTrue(
            parece_del_municipio("https://navarro.gob.ar/tramites/", "Navarro", "cualquier cosa")
        )

    def test_evidencia_con_el_nombre_del_municipio_pasa(self):
        self.assertTrue(
            parece_del_municipio(
                "https://www.facebook.com/municipionavarro/",
                "Navarro",
                "Municipalidad de Navarro - Facebook",
            )
        )

    def test_diarios_y_directorios_se_descartan(self):
        for url in (
            "https://es.wikipedia.org/wiki/Navarro",
            "https://www.govserv.org/AR/Navarro/123/Municipalidad-de-Navarro",
            "https://www.lanacion.com.ar/nota-sobre-navarro",
        ):
            with self.subTest(url=url):
                self.assertFalse(parece_del_municipio(url, "Navarro", "Navarro municipalidad"))


class TestCapa2Busqueda(unittest.TestCase):
    def test_son_las_8_queries_del_handoff(self):
        queries = construir_queries("Navarro")
        self.assertEqual(len(queries), 8)
        self.assertEqual(len(PLANTILLAS_QUERY), 8)
        self.assertIn("Municipalidad de Navarro Buenos Aires sitio oficial", queries)
        self.assertIn("Navarro gob ar reclamos 147", queries)

    def test_convierte_resultados_en_urls_con_evidencia(self):
        q = "Municipalidad de Navarro Buenos Aires sitio oficial"
        proveedor = ProveedorFijo(
            {
                q: [
                    ResultadoBusqueda(
                        url="https://navarro.gob.ar/",
                        titulo="Navarro Municipalidad",
                        snippet="Portal oficial del Municipio de Navarro",
                        posicion=1,
                        query=q,
                    )
                ]
            }
        )
        urls = buscar_urls("Navarro", "MUN-BA-004", proveedor=proveedor)
        self.assertEqual(len(urls), 1)
        u = urls[0]
        self.assertEqual(u.fuente_query, q)
        self.assertIn("Navarro Municipalidad", u.titulo_fragmento)
        self.assertIs(u.confianza, Confianza.MEDIA)  # todavia sin validar
        self.assertIs(u.estado_validacion, EstadoValidacion.PENDIENTE)

    def test_ejecuta_las_8_queries(self):
        proveedor = ProveedorFijo({})
        buscar_urls("Navarro", "MUN-BA-004", proveedor=proveedor)
        self.assertEqual(len(proveedor.queries_ejecutadas), 8)

    def test_resultado_sin_titulo_ni_snippet_se_descarta(self):
        q = "Municipalidad de Navarro Buenos Aires sitio oficial"
        proveedor = ProveedorFijo(
            {q: [ResultadoBusqueda("https://navarro.gob.ar/", "", "", 1, q)]}
        )
        self.assertEqual(buscar_urls("Navarro", "MUN-BA-004", proveedor=proveedor), [])

    def test_buscador_caido_devuelve_lista_vacia_no_urls_inventadas(self):
        self.assertEqual(buscar_urls("Navarro", "MUN-BA-004", proveedor=ProveedorFijo({})), [])


class TestCapa3Confianza(unittest.TestCase):
    def test_url_y_titulo_coinciden_da_alta(self):
        self.assertIs(
            calcular_confianza("https://navarro.gob.ar/", "Navarro", "Navarro Municipalidad"),
            Confianza.ALTA,
        )

    def test_solo_url_da_media(self):
        self.assertIs(
            calcular_confianza("https://navarro.gob.ar/x/", "Navarro", "Bienvenidos"),
            Confianza.MEDIA,
        )

    def test_ninguna_da_baja(self):
        self.assertIs(calcular_confianza("https://otro.com/", "Navarro", "Otra cosa"), Confianza.BAJA)

    def test_titulo_de_otro_municipio_no_acredita(self):
        self.assertFalse(titulo_es_del_municipio("Municipalidad de Lobos", "Navarro"))
        self.assertTrue(titulo_es_del_municipio("Municipalidad de Navarro", "Navarro"))

    def test_titulo_sin_palabra_institucional_no_acredita(self):
        self.assertFalse(titulo_es_del_municipio("Navarro Autopartes SRL", "Navarro"))

    def test_url_apunta_al_municipio(self):
        self.assertTrue(url_apunta_al_municipio("https://navarro.gob.ar/x", "Navarro"))
        self.assertTrue(url_apunta_al_municipio("https://www.gba.gob.ar/municipios/navarro", "Navarro"))
        self.assertFalse(url_apunta_al_municipio("https://ejemplo.com/", "Navarro"))

    def test_extraer_titulo(self):
        self.assertEqual(extraer_titulo("<html><title> Hola  Mundo </title></html>"), "Hola Mundo")
        self.assertEqual(
            extraer_titulo('<html><meta property="og:title" content="Desde OG"></html>'), "Desde OG"
        )
        self.assertIsNone(extraer_titulo("<html><body>sin titulo</body></html>"))


class TestSeleccionYRanking(unittest.TestCase):
    def test_recorta_a_20_por_adr_0010(self):
        urls = [
            candidata(url=f"https://navarro.gob.ar/s{i}/", tipo=TipoURL.OTRO)
            for i in range(60)
        ]
        elegidas = engine.seleccionar_top(urls)
        self.assertEqual(len(elegidas), MAX_URLS_POR_MUNICIPIO)

    def test_no_deja_afuera_al_sitio_oficial(self):
        ruido = [
            candidata(url=f"https://navarro.gob.ar/n{i}/", tipo=TipoURL.OTRO, confianza=Confianza.MEDIA)
            for i in range(40)
        ]
        oficial = candidata(
            url="https://navarro.gob.ar/",
            tipo=TipoURL.SITIO_OFICIAL,
            titulo_fragmento="Navarro Municipalidad",
            confianza=Confianza.ALTA,
            estado_validacion=EstadoValidacion.VALIDADA,
        )
        elegidas = engine.seleccionar_top(ruido + [oficial])
        self.assertIn(oficial.url, {u.url for u in elegidas})
        self.assertIs(elegidas[0].tipo, TipoURL.SITIO_OFICIAL)

    def test_un_solo_tipo_no_se_come_los_20_lugares(self):
        urls = [
            candidata(url=f"https://navarro.gob.ar/n{i}/", tipo=TipoURL.OTRO) for i in range(30)
        ] + [
            candidata(url="https://navarro.gob.ar/salud/", tipo=TipoURL.SALUD_TURNOS),
            candidata(url="https://navarro.gob.ar/tasas/", tipo=TipoURL.HACIENDA_TASAS_RAFAM),
        ]
        tipos = {u.tipo for u in engine.seleccionar_top(urls)}
        self.assertIn(TipoURL.SALUD_TURNOS, tipos)
        self.assertIn(TipoURL.HACIENDA_TASAS_RAFAM, tipos)

    def test_deduplica_quedandose_con_la_mejor_version(self):
        baja = candidata(
            url="https://navarro.gob.ar/x/",
            titulo_fragmento=None,
            confianza=Confianza.BAJA,
            estado_validacion=EstadoValidacion.NO_VERIFICABLE,
            es_oficial=None,
        )
        alta = candidata(
            url="https://navarro.gob.ar/x",  # misma URL, sin barra final
            titulo_fragmento="Tramites – Navarro Municipalidad",
            confianza=Confianza.ALTA,
            estado_validacion=EstadoValidacion.VALIDADA,
        )
        quedan = engine.deduplicar([baja, alta])
        self.assertEqual(len(quedan), 1)
        self.assertIs(quedan[0].confianza, Confianza.ALTA)


class TestPersistencia(unittest.TestCase):
    def _inventario(self, municipio="Navarro", urls=None) -> MunicipioDiscovery:
        return MunicipioDiscovery(
            municipio=municipio,
            id_municipio="MUN-BA-004",
            poblacion=19000,
            urls=urls if urls is not None else [candidata()],
        )

    def test_sqlite_cumple_el_ddl_del_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "d.sqlite"
            storage.guardar_sqlite([self._inventario()], db)
            con = sqlite3.connect(db)
            cols = [r[1] for r in con.execute("PRAGMA table_info(discovery_urls)")]
            self.assertEqual(
                cols,
                ["id", "municipio", "id_municipio", "url", "tipo", "fuente_query",
                 "titulo_fragmento", "fecha_descubrimiento", "confianza",
                 "estado_validacion", "es_oficial"],
            )
            indices = {r[1] for r in con.execute("PRAGMA index_list(discovery_urls)")}
            self.assertIn("idx_municipio", indices)
            self.assertIn("idx_tipo", indices)
            con.close()

    def test_check_de_confianza_rechaza_valores_fuera_del_enum(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "d.sqlite"
            storage.guardar_sqlite([self._inventario()], db)
            con = sqlite3.connect(db)
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute(
                    "INSERT INTO discovery_urls (id,municipio,id_municipio,url,tipo,"
                    "fecha_descubrimiento,confianza,estado_validacion) "
                    "VALUES ('x','Navarro','MUN-BA-004','https://a/','otro','2026-01-01','Altisima','validada')"
                )
            con.close()

    def test_correr_dos_veces_no_duplica(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "d.sqlite"
            storage.guardar_sqlite([self._inventario()], db)
            storage.guardar_sqlite([self._inventario()], db)
            con = sqlite3.connect(db)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM discovery_urls").fetchone()[0], 1)
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM municipios_discovery").fetchone()[0], 1
            )
            con.close()

    def test_municipio_sin_urls_igual_queda_registrado(self):
        """ADR-0009: el vacio se ve, no desaparece del archivo."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "d.sqlite"
            vacio = MunicipioDiscovery(municipio="Tordillo", id_municipio="MUN-BA-999", urls=[])
            storage.guardar_sqlite([vacio], db)
            con = sqlite3.connect(db)
            fila = con.execute(
                "SELECT municipio, total_urls, estado FROM municipios_discovery"
            ).fetchone()
            con.close()
            self.assertEqual(fila, ("Tordillo", 0, "no_encontrado"))

    def test_estado_municipio(self):
        alta = candidata(
            url="https://navarro.gob.ar/",
            tipo=TipoURL.SITIO_OFICIAL,
            titulo_fragmento="Navarro Municipalidad",
            confianza=Confianza.ALTA,
            estado_validacion=EstadoValidacion.VALIDADA,
        )
        self.assertEqual(storage.estado_municipio(self._inventario(urls=[alta])), "descubierto")
        self.assertEqual(storage.estado_municipio(self._inventario()), "parcial")
        self.assertEqual(storage.estado_municipio(self._inventario(urls=[])), "no_encontrado")

    def test_json_incluye_estado_y_totales(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.json"
            storage.guardar_json([self._inventario()], path)
            datos = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(datos["total_municipios"], 1)
            self.assertEqual(datos["total_urls"], 1)
            self.assertIn("estado", datos["municipios"][0])


class TestGuardiaDeProvincia(unittest.TestCase):
    """Hay municipios homonimos en varias provincias: Maipu, Rivadavia,
    25 de Mayo, Castelli, Colon, General Alvear. Asignarle a un municipio
    bonaerense el sitio de su homonimo seria el error que ADR-0009 prohibe."""

    def test_provincia_declarada_explicitamente_descarta(self):
        self.assertEqual(
            provincia_ajena("25 de Mayo - Provincia de San Juan | Municipalidad"), "san juan"
        )

    def test_domicilio_en_otra_provincia_descarta(self):
        self.assertEqual(
            provincia_ajena("Av. Libertador San Martin 5416, Rivadavia, San Juan, Argentina"),
            "san juan",
        )

    def test_menciones_repetidas_sin_marca_bonaerense_descartan(self):
        self.assertEqual(provincia_ajena("Maipu Municipio. Mendoza. Vivi Mendoza."), "mendoza")

    def test_una_mencion_suelta_no_alcanza(self):
        """'Neuquen 450' es una calle, no una provincia."""
        self.assertIsNone(provincia_ajena("Municipalidad de Carlos Casares. Neuquen 450."))

    def test_marca_bonaerense_gana(self):
        self.assertIsNone(
            provincia_ajena("Municipalidad de X, provincia de Buenos Aires. Mendoza 120. Mendoza 3")
        )

    def test_no_confunde_saltar_con_salta(self):
        self.assertIsNone(provincia_ajena("Saltar al contenido. Saltear este paso."))

    def test_sitio_bonaerense_limpio_pasa(self):
        self.assertIsNone(provincia_ajena("Navarro Municipalidad - Tramites y Servicios"))


class TestVariantesDeDominio(unittest.TestCase):
    def test_omite_prefijos_para_el_dominio_corto(self):
        self.assertEqual(variantes_slug("General Madariaga"), ["generalmadariaga", "madariaga"])
        self.assertEqual(variantes_slug("Carlos Casares"), ["carloscasares", "casares"])

    def test_municipio_sin_prefijo_da_una_sola_variante(self):
        self.assertEqual(variantes_slug("Navarro"), ["navarro"])

    def test_candidatos_prueban_nombre_completo_antes_que_corto(self):
        urls = [u for u, _ in candidatos_dominio("General Villegas")]
        self.assertLess(
            urls.index("https://generalvillegas.gob.ar/"), urls.index("https://villegas.gob.ar/")
        )

    def test_no_hay_candidatos_repetidos(self):
        urls = [u for u, _ in candidatos_dominio("General Alvear")]
        self.assertEqual(len(urls), len(set(urls)))


class TestHostAcreditado(unittest.TestCase):
    """Una vez acreditado el sitio del municipio, lo que viva en otro host sobra.

    Es el agujero por el que se colaba Maipu de Mendoza: las URLs de Capa 1 son
    hipotesis de dominio y la Capa 3 las ascendia a Alta mirando solo el <title>,
    sin pasar por el guardia de provincia.
    """

    def _u(self, url, tipo=TipoURL.SITIO_OFICIAL, fuente="heuristica:x"):
        return candidata(municipio="Maipu", url=url, tipo=tipo, fuente_query=fuente,
                         titulo_fragmento="Maipu Municipio")

    def test_descarta_el_homonimo_de_otra_provincia(self):
        quedan = engine.descartar_hosts_ajenos(
            [self._u("https://www.maipu-gba.gob.ar/"), self._u("https://maipu.gob.ar/")],
            "maipu-gba.gob.ar",
        )
        self.assertEqual([u.url for u in quedan], ["https://www.maipu-gba.gob.ar/"])

    def test_ignora_el_www_al_comparar(self):
        quedan = engine.descartar_hosts_ajenos([self._u("https://www.x.gob.ar/a")], "x.gob.ar")
        self.assertEqual(len(quedan), 1)

    def test_conserva_registros_provinciales(self):
        sibom = self._u(
            "https://sibom.slyt.gba.gob.ar/cities/1",
            tipo=TipoURL.BOLETIN_SIBOM,
            fuente="registro_sibom:x",
        )
        self.assertEqual(len(engine.descartar_hosts_ajenos([sibom], "maipu-gba.gob.ar")), 1)

    def test_conserva_redes_y_stores(self):
        fb = self._u("https://www.facebook.com/munimaipu/", tipo=TipoURL.FACEBOOK_OFICIAL)
        self.assertEqual(len(engine.descartar_hosts_ajenos([fb], "maipu-gba.gob.ar")), 1)

    def test_sin_sitio_acreditado_no_descarta_nada(self):
        urls = [self._u("https://a.gob.ar/"), self._u("https://b.gob.ar/")]
        self.assertEqual(len(engine.descartar_hosts_ajenos(urls, None)), 2)


class TestEsquemaHttp(unittest.TestCase):
    def test_dedup_ignora_el_esquema_y_prefiere_https(self):
        insegura = candidata(url="http://x.gob.ar/transparencia/", tipo=TipoURL.TRANSPARENCIA)
        segura = candidata(url="https://x.gob.ar/transparencia/", tipo=TipoURL.TRANSPARENCIA)
        quedan = engine.deduplicar([insegura, segura])
        self.assertEqual(len(quedan), 1)
        self.assertTrue(quedan[0].url.startswith("https://"))

    def test_sitio_sin_https_se_registra(self):
        sin_tls = MunicipioDiscovery(
            municipio="Villarino", id_municipio="MUN-BA-066",
            urls=[candidata(municipio="Villarino", url="http://www.villarino.gob.ar/",
                            tipo=TipoURL.SITIO_OFICIAL,
                            titulo_fragmento="Municipio de Villarino")],
        )
        self.assertEqual(storage.sitio_sin_https(sin_tls), 1)
        con_tls = MunicipioDiscovery(
            municipio="Navarro", id_municipio="MUN-BA-004",
            urls=[candidata(url="https://navarro.gob.ar/", tipo=TipoURL.SITIO_OFICIAL)],
        )
        self.assertEqual(storage.sitio_sin_https(con_tls), 0)
        sin_sitio = MunicipioDiscovery(municipio="X", id_municipio="MUN-BA-999", urls=[])
        self.assertIsNone(storage.sitio_sin_https(sin_sitio))


class TestResistenciaAFallas(unittest.TestCase):
    def test_una_fuente_caida_no_tumba_al_municipio(self):
        def explota(*a, **k):
            raise RuntimeError("buscador bloqueado")

        self.assertEqual(engine._sin_romper(explota, "Navarro", "MUN-BA-004"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
