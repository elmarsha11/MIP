"""
Tests Ticket 1 - Fase 3 Descubrimiento (Capa 1 + schemas).

Correr:
    python -m unittest discover -s tests -v
    python tests/test_discovery_ticket1.py

Cubre: enum cerrado, ADR-0009 (sin fragmento no hay dato), ADR-0010 (max 20),
UNIQUE(municipio, url), resolucion de id_municipio para los 86, y compatibilidad
con el sample validado de Navarro.
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "discovery"))

from pydantic import ValidationError  # noqa: E402

import discovery_engine as engine  # noqa: E402
from heuristics import PATRONES_PATH, generar_urls_heuristicas  # noqa: E402
from schemas import (  # noqa: E402
    MAX_URLS_POR_MUNICIPIO,
    Confianza,
    DiscoveryURL,
    EstadoValidacion,
    MunicipioDiscovery,
    TipoURL,
    es_https,
    generar_id,
    normalizar_slug,
)

SAMPLE_NAVARRO = PROJECT_ROOT / "data" / "processed" / "discovery" / "discovery_sample_Navarro.json"


def url_base(**kwargs) -> dict:
    datos = dict(
        municipio="Navarro",
        id_municipio="MUN-BA-004",
        url="https://navarro.gob.ar/",
        tipo=TipoURL.SITIO_OFICIAL,
        fuente_query="Municipalidad de Navarro Buenos Aires sitio oficial",
        titulo_fragmento="Navarro Municipalidad - sitio oficial",
        confianza=Confianza.ALTA,
        estado_validacion=EstadoValidacion.VALIDADA,
        es_oficial=True,
    )
    datos.update(kwargs)
    return datos


class TestNormalizacion(unittest.TestCase):
    def test_slug_quita_acentos_espacios_y_parenteticos(self):
        casos = {
            "Navarro": "navarro",
            "Coronel Suárez": "coronelsuarez",
            "Chascomús": "chascomus",
            "9 de Julio": "9dejulio",
            "San Andrés de Giles": "sanandresdegiles",
            "Saavedra (Pigüé)": "saavedra",
            "Gonzales Cháves": "gonzaleschaves",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_slug(entrada), esperado)

    def test_id_es_deterministico_y_estable_entre_corridas(self):
        a = generar_id("Navarro", "https://navarro.gob.ar/")
        b = generar_id("navarro", "https://navarro.gob.ar/")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("dis_"))
        self.assertNotEqual(a, generar_id("Navarro", "https://navarro.gob.ar/tramites/"))


class TestSchemaADR0009(unittest.TestCase):
    def test_url_sin_fragmento_no_puede_ser_alta(self):
        with self.assertRaises(ValidationError) as ctx:
            DiscoveryURL(**url_base(titulo_fragmento=None))
        self.assertIn("ADR-0009", str(ctx.exception))

    def test_url_sin_fragmento_no_puede_ser_media(self):
        with self.assertRaises(ValidationError):
            DiscoveryURL(
                **url_base(
                    titulo_fragmento=None,
                    confianza=Confianza.MEDIA,
                    estado_validacion=EstadoValidacion.NO_VERIFICABLE,
                    es_oficial=None,
                )
            )

    def test_url_sin_fragmento_no_puede_declararse_validada(self):
        with self.assertRaises(ValidationError):
            DiscoveryURL(
                **url_base(
                    titulo_fragmento=None,
                    confianza=Confianza.BAJA,
                    estado_validacion=EstadoValidacion.VALIDADA,
                    es_oficial=None,
                )
            )

    def test_url_sin_fragmento_no_puede_afirmar_es_oficial(self):
        with self.assertRaises(ValidationError):
            DiscoveryURL(
                **url_base(
                    titulo_fragmento=None,
                    confianza=Confianza.BAJA,
                    estado_validacion=EstadoValidacion.NO_VERIFICABLE,
                    es_oficial=True,
                )
            )

    def test_fragmento_en_blanco_equivale_a_ausente(self):
        with self.assertRaises(ValidationError):
            DiscoveryURL(**url_base(titulo_fragmento="   "))

    def test_candidata_sin_evidencia_es_valida_como_baja_no_verificable(self):
        u = DiscoveryURL(
            **url_base(
                titulo_fragmento=None,
                confianza=Confianza.BAJA,
                estado_validacion=EstadoValidacion.NO_VERIFICABLE,
                es_oficial=None,
            )
        )
        self.assertIsNone(u.titulo_fragmento)
        self.assertIsNone(u.es_oficial)


class TestSchemaReglasDuras(unittest.TestCase):
    def test_url_debe_ser_absoluta(self):
        for mala in ("navarro.gob.ar", "/tramites/", "ftp://navarro.gob.ar/", "https://"):
            with self.subTest(url=mala), self.assertRaises(ValidationError):
                DiscoveryURL(**url_base(url=mala))

    def test_admite_http_para_municipios_sin_tls(self):
        """ADR-0012: Rauch y Villarino solo existen en http. Exigir https los borraba."""
        u = DiscoveryURL(
            **url_base(
                url="http://www.villarino.gob.ar/",
                titulo_fragmento="Municipio de Villarino",
                municipio="Villarino",
            )
        )
        self.assertEqual(u.url, "http://www.villarino.gob.ar/")
        self.assertFalse(es_https(u.url))
        self.assertTrue(es_https("https://navarro.gob.ar/"))

    def test_tipo_fuera_del_enum_falla(self):
        with self.assertRaises(ValidationError):
            DiscoveryURL(**url_base(tipo="portal_magico"))

    def test_alta_requiere_url_del_municipio(self):
        with self.assertRaises(ValidationError):
            DiscoveryURL(
                **url_base(
                    url="https://www.lanacion.com.ar/nota",
                    titulo_fragmento="Municipalidad de Navarro en la noticia",
                )
            )

    def test_alta_requiere_evidencia_municipal_en_el_fragmento(self):
        with self.assertRaises(ValidationError):
            DiscoveryURL(**url_base(titulo_fragmento="Bienvenidos al portal"))

    def test_play_store_sin_id_de_app_falla(self):
        with self.assertRaises(ValidationError):
            DiscoveryURL(
                **url_base(
                    url="https://play.google.com/store/search?q=municipalidad",
                    tipo=TipoURL.PLAY_STORE,
                )
            )

    def test_play_store_con_id_de_app_pasa(self):
        u = DiscoveryURL(
            **url_base(
                url="https://play.google.com/store/apps/details?id=ar.gob.navarro.minavarro",
                tipo=TipoURL.PLAY_STORE,
                titulo_fragmento="Mi Navarro - Municipalidad de Navarro",
                confianza=Confianza.MEDIA,
                estado_validacion=EstadoValidacion.PENDIENTE,
            )
        )
        self.assertIs(u.tipo, TipoURL.PLAY_STORE)


class TestInventarioMunicipio(unittest.TestCase):
    def test_adr_0010_no_admite_mas_de_20_urls(self):
        urls = [
            DiscoveryURL(
                **url_base(
                    url=f"https://navarro.gob.ar/p{i}/",
                    titulo_fragmento=None,
                    confianza=Confianza.BAJA,
                    estado_validacion=EstadoValidacion.NO_VERIFICABLE,
                    es_oficial=None,
                )
            )
            for i in range(MAX_URLS_POR_MUNICIPIO + 1)
        ]
        with self.assertRaises(ValidationError) as ctx:
            MunicipioDiscovery(municipio="Navarro", id_municipio="MUN-BA-004", urls=urls)
        self.assertIn("ADR-0010", str(ctx.exception))

    def test_adr_0010_admite_menos_de_20(self):
        inv = MunicipioDiscovery(
            municipio="Navarro",
            id_municipio="MUN-BA-004",
            urls=generar_urls_heuristicas("Navarro", "MUN-BA-004"),
        )
        self.assertEqual(inv.total_urls, 5)

    def test_url_duplicada_por_municipio_falla(self):
        u = DiscoveryURL(**url_base())
        with self.assertRaises(ValidationError):
            MunicipioDiscovery(
                municipio="Navarro", id_municipio="MUN-BA-004", urls=[u, u.model_copy()]
            )

    def test_total_urls_se_recalcula_solo(self):
        inv = MunicipioDiscovery(
            municipio="Navarro",
            id_municipio="MUN-BA-004",
            total_urls=99,
            urls=[DiscoveryURL(**url_base())],
        )
        self.assertEqual(inv.total_urls, 1)


class TestHeuristicaCapa1(unittest.TestCase):
    def test_navarro_devuelve_5_urls_del_dominio_correcto(self):
        urls = generar_urls_heuristicas("Navarro", "MUN-BA-004")
        self.assertEqual(len(urls), 5)
        self.assertEqual(urls[0].url, "https://navarro.gob.ar/")
        self.assertIs(urls[0].tipo, TipoURL.SITIO_OFICIAL)
        self.assertEqual(
            [u.tipo for u in urls], [tipo for _, tipo, _ in PATRONES_PATH]
        )

    def test_ninguna_url_heuristica_inventa_evidencia(self):
        for nombre in ("Navarro", "Coronel Suárez", "9 de Julio"):
            for u in generar_urls_heuristicas(nombre, "MUN-BA-000"):
                with self.subTest(municipio=nombre, url=u.url):
                    self.assertIsNone(u.titulo_fragmento)
                    self.assertIs(u.confianza, Confianza.BAJA)
                    self.assertIs(u.estado_validacion, EstadoValidacion.NO_VERIFICABLE)
                    self.assertIsNone(u.es_oficial)
                    self.assertTrue(u.fuente_query.startswith("heuristica:"))

    def test_dominios_alternativos_son_opcionales(self):
        urls = generar_urls_heuristicas(
            "Navarro", "MUN-BA-004", incluir_dominios_alternativos=True
        )
        self.assertEqual(len(urls), 15)
        self.assertIn("https://muninavarro.gob.ar/", {u.url for u in urls})


class TestGoldStandard(unittest.TestCase):
    def test_carga_86_municipios_con_id(self):
        municipios = engine.cargar_municipios()
        self.assertEqual(len(municipios), engine.TOTAL_MUNICIPIOS_ESPERADO)
        self.assertEqual(len({m.nombre for m in municipios}), 86)
        for m in municipios:
            with self.subTest(municipio=m.nombre):
                self.assertRegex(m.id_municipio, r"^MUN-BA-\d{3}$")

    def test_ids_no_se_repiten(self):
        ids = [m.id_municipio for m in engine.cargar_municipios()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_navarro_es_mun_ba_004(self):
        self.assertEqual(engine.buscar_municipio("Navarro").id_municipio, "MUN-BA-004")

    def test_busqueda_tolera_acentos_y_mayusculas(self):
        self.assertEqual(engine.buscar_municipio("chascomus").nombre, "Chascomús")
        self.assertEqual(engine.buscar_municipio("CORONEL SUAREZ").nombre, "Coronel Suárez")

    def test_municipio_inexistente_falla_en_vez_de_inventar(self):
        with self.assertRaises(ValueError):
            engine.buscar_municipio("Springfield")

    def test_poblacion_ausente_es_none_no_cero(self):
        for m in engine.cargar_municipios():
            with self.subTest(municipio=m.nombre):
                self.assertTrue(m.poblacion is None or m.poblacion > 0)


class TestInvestigarNavarro(unittest.TestCase):
    """Capa 1 aislada: sin red, el motor no puede afirmar nada."""

    @classmethod
    def setUpClass(cls):
        inicio = time.perf_counter()
        cls.resultado = engine.investigar(
            "Navarro", con_sitio=False, con_registros=False,
            con_busqueda=False, con_validacion=False,
        )
        cls.duracion = time.perf_counter() - inicio

    def test_termina_en_menos_de_120_segundos(self):
        self.assertLess(self.duracion, 120)

    def test_devuelve_5_urls_con_id_correcto(self):
        self.assertEqual(self.resultado.total_urls, 5)
        self.assertEqual(self.resultado.id_municipio, "MUN-BA-004")
        self.assertEqual(self.resultado.municipio, "Navarro")

    def test_incluye_el_sitio_oficial_del_gold_standard(self):
        oficiales = {u.url for u in self.resultado.por_tipo(TipoURL.SITIO_OFICIAL)}
        self.assertIn("https://navarro.gob.ar/", oficiales)

    def test_incluye_tramites_y_transparencia(self):
        tipos = {u.tipo for u in self.resultado.urls}
        self.assertIn(TipoURL.TRAMITES, tipos)
        self.assertIn(TipoURL.TRANSPARENCIA, tipos)

    def test_no_hay_urls_duplicadas(self):
        urls = [u.url for u in self.resultado.urls]
        self.assertEqual(len(urls), len(set(urls)))

    def test_ticket1_no_afirma_confianza_alta(self):
        """Sin Capa 2/3 no hay evidencia, asi que nada puede ser Alta ni Media."""
        self.assertEqual(self.resultado.por_confianza(Confianza.ALTA), [])
        self.assertEqual(self.resultado.por_confianza(Confianza.MEDIA), [])
        self.assertEqual(self.resultado.con_evidencia(), [])

    def test_serializa_a_json_con_las_columnas_del_schema(self):
        columnas = {
            "id",
            "municipio",
            "id_municipio",
            "url",
            "tipo",
            "fuente_query",
            "titulo_fragmento",
            "fecha_descubrimiento",
            "confianza",
            "estado_validacion",
            "es_oficial",
        }
        for u in self.resultado.urls:
            self.assertEqual(set(u.to_row()), columnas)
        json.dumps(self.resultado.model_dump(mode="json"), ensure_ascii=False)


class TestCompatibilidadSampleNavarro(unittest.TestCase):
    """El sample validado de Fase 3 tiene que seguir pasando el schema."""

    def test_sample_navarro_valida_contra_el_schema(self):
        if not SAMPLE_NAVARRO.exists():
            self.skipTest(f"No existe {SAMPLE_NAVARRO}")
        datos = json.loads(SAMPLE_NAVARRO.read_text(encoding="utf-8"))
        for fila in datos["urls"]:
            with self.subTest(url=fila["url"]):
                DiscoveryURL(
                    municipio=datos["municipio"],
                    id_municipio=datos["id_municipio"],
                    url=fila["url"],
                    tipo=fila["tipo"],
                    fuente_query=fila["fuente_query"],
                    titulo_fragmento=fila["titulo_fragmento"],
                    confianza=fila["confianza"],
                    estado_validacion=fila["estado_validacion"],
                    es_oficial=fila["es_oficial"],
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
