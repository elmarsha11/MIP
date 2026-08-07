"""
Fase 3 - Discovery Engine (orquestador de las 3 capas).

    Capa 1 - heuristica    heuristics.py       URLs probables desde el nombre
    Capa 2 - tres fuentes independientes (ADR-0011):
             sitio         site_crawler.py     dominio oficial + enlaces de su home
             registros     registries.py       SIBOM y ficha provincial
             busqueda      search_provider.py  las 8 queries del HANDOFF
    Capa 3 - validacion    validator.py        HTTP 200 + <title>, define confianza

Uso:
    python src/discovery/discovery_engine.py --municipio Navarro
    python src/discovery/discovery_engine.py --all
    python src/discovery/discovery_engine.py --municipio Navarro --solo-heuristica
    python src/discovery/discovery_engine.py --listar-municipios

Contratos: decisions/ADR-0009, ADR-0010, ADR-0011, schemas/discovery_schema.md
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence
from urllib.parse import urlparse

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

try:  # ejecutado como paquete
    from .heuristics import es_url_heuristica, generar_urls_heuristicas
    from .schemas import (
        MAX_URLS_POR_MUNICIPIO,
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        MunicipioDiscovery,
        TipoURL,
        ahora_iso,
        es_https,
        normalizar_slug,
        normalizar_texto,
    )
    from .registries import (
        cargar_indice_sibom,
        pistas_de_sitio_oficial,
        urls_de_registros,
    )
    from .search_provider import DuckDuckGoProvider, buscar_urls
    from .site_crawler import descubrir_sitio
    from .storage import estado_municipio, guardar_json, guardar_sqlite
    from .validator import validar_lote
except ImportError:  # ejecutado como script
    from heuristics import es_url_heuristica, generar_urls_heuristicas  # type: ignore[no-redef]
    from schemas import (  # type: ignore[no-redef]
        MAX_URLS_POR_MUNICIPIO,
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        MunicipioDiscovery,
        TipoURL,
        ahora_iso,
        es_https,
        normalizar_slug,
        normalizar_texto,
    )
    from registries import (  # type: ignore[no-redef]
        cargar_indice_sibom,
        pistas_de_sitio_oficial,
        urls_de_registros,
    )
    from search_provider import DuckDuckGoProvider, buscar_urls  # type: ignore[no-redef]
    from site_crawler import descubrir_sitio  # type: ignore[no-redef]
    from storage import estado_municipio, guardar_json, guardar_sqlite  # type: ignore[no-redef]
    from validator import validar_lote  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

PROJECT_ROOT = _AQUI.parents[1]
GOLD_STANDARD_CSV = PROJECT_ROOT / "data" / "processed" / "gold_standard_86.csv"
# Unico uso permitido del draft IA: el mapeo nombre -> ID_Municipio (identidad,
# no variable medida). gold_standard_86.csv no trae la columna de ID y el
# HANDOFF exige id_municipio en cada fila (Navarro = MUN-BA-004).
# Las columnas de variables de este archivo siguen en cuarentena por ADR-0009.
MATRIZ_IDS_CSV = PROJECT_ROOT / "data" / "processed" / "Matriz-86-municipios.csv"
DISCOVERY_DIR = PROJECT_ROOT / "data" / "processed" / "discovery"
JSON_86 = DISCOVERY_DIR / "discovery_urls_86.json"
SQLITE_86 = DISCOVERY_DIR / "discovery_urls_86.sqlite"

TOTAL_MUNICIPIOS_ESPERADO = 86  # Fase 2 cerrada: 86 unicos (041 y 052 eliminados)

# Nombres que difieren entre el Gold Standard y la matriz de IDs. Mapeo explicito
# y auditable en vez de fuzzy match, para no asignarle el ID equivocado a un municipio.
# Los otros 4 desajustes (acentos y parenteticos) los resuelve normalizar_slug.
ALIAS_ID_MUNICIPIO = {
    "alem": "leandro n. alem",
}

# Prioridad de tipos al recortar a 20 (ADR-0010). Lo primero que necesita el
# investigador es el sitio y sus servicios; las redes y stores van al final.
PRIORIDAD_TIPO = {
    TipoURL.SITIO_OFICIAL: 0,
    TipoURL.TRAMITES: 1,
    TipoURL.TRANSPARENCIA: 2,
    TipoURL.SALUD_TURNOS: 3,
    TipoURL.HACIENDA_TASAS_RAFAM: 4,
    TipoURL.RECLAMOS_147: 5,
    TipoURL.BOLETIN_SIBOM: 6,
    TipoURL.GDE_EXPEDIENTE: 7,
    TipoURL.NORMATIVA_ORDENANZAS: 8,
    TipoURL.LICITACIONES: 9,
    TipoURL.PLAY_STORE: 10,
    TipoURL.APP_STORE: 11,
    TipoURL.FACEBOOK_OFICIAL: 12,
    TipoURL.INSTAGRAM_OFICIAL: 13,
    TipoURL.YOUTUBE_OFICIAL: 14,
    TipoURL.OTRO: 15,
}
PRIORIDAD_CONFIANZA = {Confianza.ALTA: 0, Confianza.MEDIA: 1, Confianza.BAJA: 2, Confianza.CERO: 3}
MAX_POR_TIPO = 4  # que un solo tipo no se coma los 20 lugares

# Tipos que por definicion no viven en el dominio del municipio.
TIPOS_FUERA_DEL_SITIO = frozenset(
    {
        TipoURL.FACEBOOK_OFICIAL,
        TipoURL.INSTAGRAM_OFICIAL,
        TipoURL.YOUTUBE_OFICIAL,
        TipoURL.PLAY_STORE,
        TipoURL.APP_STORE,
        TipoURL.BOLETIN_SIBOM,
    }
)


class Municipio(NamedTuple):
    nombre: str  # nombre exacto del Gold Standard
    id_municipio: str
    poblacion: Optional[int]


# ---------------------------------------------------------------------------
# Carga del Gold Standard
# ---------------------------------------------------------------------------


def _leer_csv(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"No se encontro {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _cargar_mapa_ids() -> Dict[str, str]:
    """slug normalizado -> ID_Municipio."""
    mapa: Dict[str, str] = {}
    for fila in _leer_csv(MATRIZ_IDS_CSV):
        nombre = (fila.get("Municipio") or "").strip()
        id_mun = (fila.get("ID_Municipio") or "").strip()
        if nombre and id_mun:
            mapa[normalizar_slug(nombre)] = id_mun
    return mapa


def _a_entero(valor: Optional[str]) -> Optional[int]:
    """'52607.0' -> 52607. Vacio -> None (ADR-0009: vacio no es 0)."""
    if valor is None or not str(valor).strip():
        return None
    try:
        return int(float(valor))
    except ValueError:
        return None


def cargar_municipios() -> List[Municipio]:
    """Los 86 municipios del Gold Standard, con su ID resuelto.

    Falla ruidosamente si algun municipio se queda sin ID: preferimos no correr
    antes que emitir filas con un id_municipio inventado.
    """
    mapa_ids = _cargar_mapa_ids()
    municipios: List[Municipio] = []
    sin_id: List[str] = []

    for fila in _leer_csv(GOLD_STANDARD_CSV):
        nombre = (fila.get("Municipio") or "").strip()
        if not nombre:
            continue
        slug = normalizar_slug(nombre)
        id_mun = mapa_ids.get(slug)
        if id_mun is None:
            alias = ALIAS_ID_MUNICIPIO.get(slug)
            if alias:
                id_mun = mapa_ids.get(normalizar_slug(alias))
        if id_mun is None:
            sin_id.append(nombre)
            continue
        municipios.append(
            Municipio(
                nombre=nombre,
                id_municipio=id_mun,
                poblacion=_a_entero(fila.get("Cant. Habitantes")),
            )
        )

    if sin_id:
        raise ValueError(
            "Municipios del Gold Standard sin ID_Municipio en "
            f"{MATRIZ_IDS_CSV.name}: {sin_id}. Agregalos a ALIAS_ID_MUNICIPIO; "
            "no se generan IDs nuevos."
        )
    if len(municipios) != TOTAL_MUNICIPIOS_ESPERADO:
        raise ValueError(
            f"Se esperaban {TOTAL_MUNICIPIOS_ESPERADO} municipios en "
            f"{GOLD_STANDARD_CSV.name}, se leyeron {len(municipios)}"
        )
    return municipios


def buscar_municipio(nombre: str) -> Municipio:
    """Busca un municipio por nombre tolerando acentos y mayusculas."""
    objetivo = normalizar_slug(nombre)
    municipios = cargar_municipios()
    for m in municipios:
        if normalizar_slug(m.nombre) == objetivo:
            return m
    parciales = [m for m in municipios if objetivo and objetivo in normalizar_slug(m.nombre)]
    if len(parciales) == 1:
        return parciales[0]
    if parciales:
        raise ValueError(
            f"{nombre!r} es ambiguo: {[m.nombre for m in parciales]}. Usa el nombre exacto."
        )
    raise ValueError(
        f"{nombre!r} no esta en el Gold Standard ({GOLD_STANDARD_CSV.name}). "
        "Corre --listar-municipios para ver los 86 nombres validos."
    )


# ---------------------------------------------------------------------------
# Seleccion y deduplicacion
# ---------------------------------------------------------------------------


def _clave_url(url: str) -> str:
    """Clave de deduplicacion: sin esquema y sin barra final.

    http://x/transparencia/ y https://x/transparencia/ son la misma pagina. Se
    guarda una sola; el _score prefiere la version https.
    """
    return url.split("://", 1)[-1].rstrip("/").lower()


def _sin_romper(funcion, *args, **kwargs) -> List[DiscoveryURL]:
    """Corre una fuente de Capa 2 y devuelve [] si se cae.

    Cada fuente es independiente: que el buscador este bloqueado no puede dejar
    al municipio sin las URLs que si consiguio el portal oficial.
    """
    try:
        return list(funcion(*args, **kwargs))
    except Exception as exc:
        print(f"    [fuente caida] {funcion.__name__}: {type(exc).__name__}: {exc}")
        return []


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def descartar_hosts_ajenos(
    urls: Sequence[DiscoveryURL], host_oficial: Optional[str]
) -> List[DiscoveryURL]:
    """Una vez acreditado el sitio del municipio, lo que viva en otro host sobra.

    Cierra el agujero por el que se colaba el homonimo de otra provincia: las
    URLs de la Capa 1 son puras hipotesis de dominio ({slug}.gob.ar) y la Capa 3
    las asciende a Alta con solo mirar el <title>, sin pasar por el guardia de
    provincia. Maipu de Mendoza entraba por ahi.

    Se conservan los registros provinciales y las redes/stores: viven en otro
    host por definicion.
    """
    if not host_oficial:
        return list(urls)

    conservados: List[DiscoveryURL] = []
    for u in urls:
        de_registro = u.fuente_query.startswith("registro_")
        if _host(u.url) == host_oficial or de_registro or u.tipo in TIPOS_FUERA_DEL_SITIO:
            conservados.append(u)
        else:
            print(
                f"    [descartado] {u.url} no pertenece al sitio acreditado "
                f"({host_oficial})"
            )
    return conservados


def _sin_valor(funcion, *args, **kwargs):
    """Igual que _sin_romper pero para fuentes que devuelven un valor unico."""
    try:
        return funcion(*args, **kwargs)
    except Exception as exc:
        print(f"    [fuente caida] {funcion.__name__}: {type(exc).__name__}: {exc}")
        return None


def _score(u: DiscoveryURL) -> tuple:
    """Menor es mejor."""
    return (
        0 if u.es_oficial else 1,
        PRIORIDAD_CONFIANZA[u.confianza],
        0 if u.estado_validacion is EstadoValidacion.VALIDADA else 1,
        0 if u.titulo_fragmento else 1,
        PRIORIDAD_TIPO.get(u.tipo, 99),
        0 if es_https(u.url) else 1,  # a igualdad de todo, https gana
        len(u.url),
    )


def deduplicar(urls: Sequence[DiscoveryURL]) -> List[DiscoveryURL]:
    """UNIQUE(municipio, url). Gana la version con mejor score."""
    mejores: Dict[tuple, DiscoveryURL] = {}
    for u in urls:
        clave = (normalizar_texto(u.municipio), _clave_url(u.url))
        actual = mejores.get(clave)
        if actual is None or _score(u) < _score(actual):
            mejores[clave] = u
    return list(mejores.values())


def seleccionar_top(
    urls: Sequence[DiscoveryURL], maximo: int = MAX_URLS_POR_MUNICIPIO
) -> List[DiscoveryURL]:
    """Recorta a `maximo` URLs (ADR-0010) cuidando la diversidad de tipos.

    Primero una pasada con tope por tipo, para que 12 notas de prensa no dejen
    afuera al turnero de salud. Si sobran lugares, se rellena con el resto.
    """
    ordenadas = sorted(urls, key=_score)
    elegidas: List[DiscoveryURL] = []
    por_tipo: Dict[TipoURL, int] = {}

    for u in ordenadas:
        if len(elegidas) >= maximo:
            break
        if por_tipo.get(u.tipo, 0) >= MAX_POR_TIPO:
            continue
        por_tipo[u.tipo] = por_tipo.get(u.tipo, 0) + 1
        elegidas.append(u)

    if len(elegidas) < maximo:
        ya = {id(u) for u in elegidas}
        for u in ordenadas:
            if len(elegidas) >= maximo:
                break
            if id(u) not in ya:
                elegidas.append(u)
    return sorted(elegidas, key=_score)


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------


def investigar(
    municipio: str,
    id_municipio: Optional[str] = None,
    poblacion: Optional[int] = None,
    con_sitio: bool = True,
    con_registros: bool = True,
    con_busqueda: bool = True,
    con_validacion: bool = True,
    proveedor=None,
    maximo: int = MAX_URLS_POR_MUNICIPIO,
    verbose: bool = False,
) -> MunicipioDiscovery:
    """Devuelve el inventario de URLs de un municipio, con trazabilidad completa.

    Capa 2 tiene tres fuentes independientes; si una falla las otras siguen:
      - sitio    : dominio oficial acreditado + enlaces de su home (fuente primaria)
      - registros: SIBOM y ficha provincial gba.gob.ar
      - busqueda : las 8 queries del HANDOFF (complementaria, degradable)

    Si corre la Capa 3, las URLs que nunca consiguieron evidencia se descartan:
    eran hipotesis de la Capa 1 y el pipeline ya las puso a prueba. Quedan las
    que tienen fragmento, tal como exige ADR-0009.
    """
    inicio = time.perf_counter()

    if id_municipio is None or poblacion is None:
        registro = buscar_municipio(municipio)
        municipio = registro.nombre  # nombre exacto del Gold Standard
        id_municipio = id_municipio or registro.id_municipio
        poblacion = poblacion if poblacion is not None else registro.poblacion

    fecha = ahora_iso()
    urls: List[DiscoveryURL] = list(generar_urls_heuristicas(municipio, id_municipio, fecha=fecha))
    host_oficial: Optional[str] = None
    if verbose:
        print(f"  capa 1 heuristica : {len(urls)} URLs probables")

    if con_sitio:
        # SIBOM y Wikidata publican el sitio web del municipio. Valen mas que
        # cualquier patron adivinado, sobre todo cuando el dominio no se parece
        # al nombre (Villa Gesell -> gesell.gob.ar, Tordillo -> tordillomunicipio.org).
        pistas = _sin_romper(pistas_de_sitio_oficial, municipio) if con_registros else []
        del_sitio = _sin_romper(
            descubrir_sitio,
            municipio,
            id_municipio,
            fecha=fecha,
            candidatos_extra=pistas,
        )
        urls.extend(del_sitio)
        if del_sitio:
            host_oficial = _host(del_sitio[0].url)  # el primero es la home acreditada
        if verbose:
            print(f"  capa 2 sitio      : {len(del_sitio)} URLs del portal oficial")

    if con_registros:
        de_registros = _sin_romper(urls_de_registros, municipio, id_municipio, fecha=fecha)
        urls.extend(de_registros)
        if verbose:
            print(f"  capa 2 registros  : {len(de_registros)} URLs de SIBOM/Provincia")

    if con_busqueda:
        encontradas = _sin_romper(
            buscar_urls, municipio, id_municipio, proveedor=proveedor, fecha=fecha
        )
        urls.extend(encontradas)
        if verbose:
            print(f"  capa 2 busqueda   : {len(encontradas)} URLs de buscador")

    urls = descartar_hosts_ajenos(deduplicar(urls), host_oficial)

    if con_validacion:
        urls = validar_lote(urls)
        # Una hipotesis que se puso a prueba y no dio evidencia no es una URL.
        antes = len(urls)
        urls = [u for u in urls if u.titulo_fragmento]
        if verbose:
            print(
                f"  capa 3 validacion : {len(urls)} con evidencia "
                f"({antes - len(urls)} hipotesis descartadas)"
            )

    urls = seleccionar_top(deduplicar(urls), maximo=maximo)

    return MunicipioDiscovery(
        municipio=municipio,
        id_municipio=id_municipio,
        poblacion=poblacion,
        fecha_descubrimiento=fecha,
        tiempo_ejecucion_segundos=round(time.perf_counter() - inicio, 2),
        urls=urls,
    )


def municipios_sin_sitio(sqlite_path: Path) -> set:
    """Nombres que en el SQLite no tienen sitio_oficial.

    Permite reintentar solo esos: los portales municipales caidos o lentos varian
    de un dia al otro, y una corrida completa para 2 municipios es desperdicio.
    Como el guardado fusiona por municipio, reintentar no toca a los demas.
    """
    import sqlite3

    if not Path(sqlite_path).exists():
        return set()
    con = sqlite3.connect(sqlite_path)
    try:
        return {
            fila[0]
            for fila in con.execute(
                "SELECT municipio FROM municipios_discovery WHERE tiene_sitio_oficial = 0"
            )
        }
    except sqlite3.Error:
        return set()
    finally:
        con.close()


def precalentar_pistas(municipios: Sequence[Municipio], verbose: bool = True) -> int:
    """Consulta SIBOM y Wikidata en serie, antes de paralelizar los municipios.

    Wikidata limita los pedidos concurrentes: con 5 workers devolvia vacio y las
    pistas se perdian en silencio, dejando sin sitio oficial a municipios que si
    lo tienen (Rauch, Tordillo). En serie tarda un minuto y no falla. Los
    resultados quedan cacheados en disco, asi que solo se paga la primera vez.
    """
    cargar_indice_sibom()
    encontradas = 0
    for m in municipios:
        if _sin_romper(pistas_de_sitio_oficial, m.nombre):
            encontradas += 1
    if verbose:
        print(f"Pistas de registros: {encontradas}/{len(municipios)} municipios\n")
    return encontradas


def investigar_todos(
    municipios: Optional[Sequence[Municipio]] = None,
    workers: int = 4,
    con_sitio: bool = True,
    con_registros: bool = True,
    con_busqueda: bool = True,
    con_validacion: bool = True,
    proveedor=None,
    verbose: bool = True,
) -> List[MunicipioDiscovery]:
    """Procesa los 86 municipios. El proveedor se comparte para respetar el
    limite de pedidos al buscador desde todos los hilos."""
    municipios = list(municipios if municipios is not None else cargar_municipios())
    proveedor = proveedor or DuckDuckGoProvider()

    if con_registros:
        precalentar_pistas(municipios, verbose=verbose)

    total = len(municipios)
    hechos = 0
    inicio = time.perf_counter()

    def _uno(m: Municipio) -> MunicipioDiscovery:
        nonlocal hechos
        try:
            r = investigar(
                m.nombre,
                id_municipio=m.id_municipio,
                poblacion=m.poblacion,
                con_sitio=con_sitio,
                con_registros=con_registros,
                con_busqueda=con_busqueda,
                con_validacion=con_validacion,
                proveedor=proveedor,
            )
        except Exception as exc:  # un municipio que falla no tumba la corrida
            print(f"  [ERROR] {m.nombre}: {type(exc).__name__}: {exc}")
            r = MunicipioDiscovery(
                municipio=m.nombre, id_municipio=m.id_municipio, poblacion=m.poblacion, urls=[]
            )
        hechos += 1
        if verbose:
            transcurrido = time.perf_counter() - inicio
            print(
                f"  [{hechos:>2}/{total}] {m.nombre:<26} {r.total_urls:>2} URLs  "
                f"{estado_municipio(r):<13} ({transcurrido / 60:.1f} min)",
                flush=True,
            )
        return r

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        resultados = list(pool.map(_uno, municipios))
    return resultados


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resumen_municipio(r: MunicipioDiscovery) -> str:
    lineas = [
        f"{r.municipio} [{r.id_municipio}] - {r.total_urls} URLs en "
        f"{r.tiempo_ejecucion_segundos}s - estado: {estado_municipio(r)}"
    ]
    for u in r.urls:
        lineas.append(
            f"  - {u.tipo.value:<22} {u.url}  [{u.confianza.value}/{u.estado_validacion.value}]"
        )
        lineas.append(f"      query:     {u.fuente_query}")
        lineas.append(f"      evidencia: {(u.titulo_fragmento or '(sin fragmento)')[:100]}")
    lineas.append(
        f"  Con evidencia: {len(r.con_evidencia())}/{r.total_urls} | "
        f"Alta: {len(r.por_confianza(Confianza.ALTA))} | "
        f"Media: {len(r.por_confianza(Confianza.MEDIA))} | "
        f"Baja: {len(r.por_confianza(Confianza.BAJA))}"
    )
    return "\n".join(lineas)


def _resumen_global(resultados: Sequence[MunicipioDiscovery]) -> str:
    estados: Dict[str, int] = {}
    for r in resultados:
        e = estado_municipio(r)
        estados[e] = estados.get(e, 0) + 1
    total_urls = sum(r.total_urls for r in resultados)
    sin_nada = [r.municipio for r in resultados if r.total_urls == 0]
    lineas = [
        "",
        "=" * 72,
        f"Municipios procesados : {len(resultados)}",
        f"URLs totales          : {total_urls}",
        f"Promedio por municipio: {total_urls / len(resultados):.1f}" if resultados else "",
        f"Con sitio oficial Alta: {estados.get('descubierto', 0)}",
        f"Parciales             : {estados.get('parcial', 0)}",
        f"Sin nada verificable  : {estados.get('no_encontrado', 0)}",
    ]
    if sin_nada:
        lineas.append(f"  ADR-0009 - quedan como No Encontrado, no como 0: {', '.join(sin_nada)}")
    lineas.append("=" * 72)
    return "\n".join(l for l in lineas if l != "")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="MIP Fase 3 - Descubrimiento de URLs municipales",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--municipio", help="Nombre del municipio (ej: Navarro)")
    grupo.add_argument("--all", action="store_true", help="Los 86 municipios del Gold Standard")
    grupo.add_argument("--listar-municipios", action="store_true", help="Lista los 86 nombres validos")
    grupo.add_argument(
        "--faltantes",
        action="store_true",
        help="Reintenta solo los municipios sin sitio oficial en el SQLite y fusiona",
    )

    parser.add_argument("--solo-heuristica", action="store_true", help="Solo Capa 1 (sin red)")
    parser.add_argument("--sin-sitio", action="store_true", help="No cosechar el portal oficial")
    parser.add_argument("--sin-registros", action="store_true", help="No consultar SIBOM/Provincia")
    parser.add_argument("--sin-busqueda", action="store_true", help="No usar buscador web")
    parser.add_argument("--sin-validar", action="store_true", help="Saltea la Capa 3")
    parser.add_argument("--offline", action="store_true", help="Buscador solo desde cache")
    parser.add_argument("--workers", type=int, default=4, help="Municipios en paralelo (--all)")
    parser.add_argument("--limite", type=int, help="Procesar solo los primeros N municipios")
    parser.add_argument("--json", type=Path, help="Ruta del JSON de salida")
    parser.add_argument("--sqlite", type=Path, help="Ruta del SQLite de salida")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.listar_municipios:
        for m in cargar_municipios():
            print(f"{m.id_municipio}\t{m.nombre}\t{m.poblacion if m.poblacion is not None else ''}")
        return 0

    con_sitio = not (args.sin_sitio or args.solo_heuristica)
    con_registros = not (args.sin_registros or args.solo_heuristica)
    con_busqueda = not (args.sin_busqueda or args.solo_heuristica)
    con_validacion = not (args.sin_validar or args.solo_heuristica)
    proveedor = DuckDuckGoProvider(offline=args.offline) if con_busqueda else None

    inicio = time.perf_counter()

    if args.municipio:
        resultado = investigar(
            args.municipio,
            con_sitio=con_sitio,
            con_registros=con_registros,
            con_busqueda=con_busqueda,
            con_validacion=con_validacion,
            proveedor=proveedor,
            verbose=True,
        )
        print(_resumen_municipio(resultado))
        resultados = [resultado]
        json_path = args.json
        sqlite_path = args.sqlite
    else:
        municipios = cargar_municipios()
        if args.faltantes:
            pendientes = municipios_sin_sitio(args.sqlite or SQLITE_86)
            if not pendientes:
                print("No hay municipios sin sitio oficial. Nada que reintentar.")
                return 0
            municipios = [m for m in municipios if m.nombre in pendientes]
            print(f"Reintentando {len(municipios)}: {', '.join(m.nombre for m in municipios)}")
        if args.limite:
            municipios = municipios[: args.limite]
        print(f"Procesando {len(municipios)} municipios con {args.workers} workers...\n")
        resultados = investigar_todos(
            municipios,
            workers=args.workers,
            con_sitio=con_sitio,
            con_registros=con_registros,
            con_busqueda=con_busqueda,
            con_validacion=con_validacion,
            proveedor=proveedor,
        )
        print(_resumen_global(resultados))
        json_path = args.json or JSON_86
        sqlite_path = args.sqlite or SQLITE_86

    if json_path:
        print(f"\nJSON   -> {guardar_json(resultados, json_path)}")
    if sqlite_path:
        print(f"SQLite -> {guardar_sqlite(resultados, sqlite_path)}")

    print(f"\nTiempo total: {time.perf_counter() - inicio:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
