"""
Fase 4 - Motor de extraccion (orquestador y CLI).

    Fase 3 encontro DONDE mirar. Fase 4 lee esas paginas y reporta QUE DICEN.

Uso:
    python src/extraction/extraction_engine.py --municipio Navarro
    python src/extraction/extraction_engine.py --all
    python src/extraction/extraction_engine.py --municipio Navarro --sin-ia

Contratos: ADR-0009, ADR-0014, schemas/diccionario_datos_oficial_v1.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
for _ruta in (_AQUI, PROJECT_ROOT / "src" / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

# Fase 3 (src/discovery). Sus modelos se llaman schemas.py; los de Fase 4 se
# llaman modelos.py justamente para que los dos puedan convivir en el path.
from discovery_engine import buscar_municipio, cargar_municipios  # noqa: E402
from schemas import ahora_iso  # noqa: E402

from extractor import extraer  # noqa: E402
from fetcher import (  # noqa: E402
    SQLITE_DISCOVERY,
    leer_paginas,
    paginas_de_turnos,
    todas_las_urls,
)
from gemini_client import ClienteGemini, CuotaAgotada  # noqa: E402
from modelos import EstadoHallazgo, MunicipioExtraccion, Variable  # noqa: E402

EXTRACTION_DIR = PROJECT_ROOT / "data" / "processed" / "extraction"
JSON_86 = EXTRACTION_DIR / "hallazgos_86.json"
SQLITE_86 = EXTRACTION_DIR / "hallazgos_86.sqlite"

DDL = """
CREATE TABLE IF NOT EXISTS hallazgos (
    id TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    variable TEXT NOT NULL,
    valor TEXT NOT NULL,
    detalle TEXT,
    url TEXT,
    fecha TEXT NOT NULL,
    fragmento TEXT,
    tipo_fuente TEXT,
    confianza TEXT NOT NULL CHECK(confianza IN ('Alta','Media','Baja','0%')),
    estado TEXT NOT NULL,
    modelo TEXT,
    UNIQUE(id_municipio, variable)
);
CREATE INDEX IF NOT EXISTS idx_hal_municipio ON hallazgos(municipio);
CREATE INDEX IF NOT EXISTS idx_hal_variable ON hallazgos(variable);

CREATE TABLE IF NOT EXISTS municipios_extraccion (
    id_municipio TEXT PRIMARY KEY,
    municipio TEXT NOT NULL UNIQUE,
    fecha TEXT NOT NULL,
    paginas_leidas INTEGER NOT NULL,
    caracteres_analizados INTEGER NOT NULL,
    llamadas_ia INTEGER NOT NULL,
    verificados INTEGER NOT NULL,
    citas_rechazadas INTEGER NOT NULL
);
"""

COLUMNAS = (
    "id", "municipio", "id_municipio", "variable", "valor", "detalle", "url",
    "fecha", "fragmento", "tipo_fuente", "confianza", "estado", "modelo",
)


# ---------------------------------------------------------------------------
# Reanudacion
# ---------------------------------------------------------------------------


def ya_extraidos(sqlite_path: Path = SQLITE_86) -> set:
    """Municipios que ya tienen al menos una variable con evidencia.

    La cuota gratuita no alcanza para los 86 de una sentada, asi que la corrida
    tiene que poder retomarse. Un municipio procesado sin ningun hallazgo se
    reintenta: pudo ser una corrida donde la IA no llego a responder.
    """
    if not Path(sqlite_path).exists():
        return set()
    con = sqlite3.connect(sqlite_path)
    try:
        return {
            f[0]
            for f in con.execute(
                "SELECT municipio FROM hallazgos WHERE estado = 'verificado' "
                "GROUP BY municipio"
            )
        }
    except sqlite3.Error:
        return set()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------


def procesar(
    municipio: str,
    id_municipio: Optional[str] = None,
    cliente=None,
    sqlite_discovery: Path = SQLITE_DISCOVERY,
    verbose: bool = False,
) -> MunicipioExtraccion:
    """Lee las paginas del municipio y extrae sus variables con evidencia."""
    if id_municipio is None:
        registro = buscar_municipio(municipio)
        municipio, id_municipio = registro.nombre, registro.id_municipio

    fecha = ahora_iso()
    urls_tipificadas = todas_las_urls(municipio, sqlite_discovery)
    paginas = leer_paginas(municipio, sqlite_discovery)
    # Cosecha dirigida: los turneros suelen estar a un nivel de profundidad, no
    # en la home. Sin esto se perdian 4 municipios que el Gold Standard marca
    # con turnos online.
    ya = {p.url for p in paginas}
    paginas += [p for p in paginas_de_turnos(municipio, sqlite_discovery) if p.url not in ya]
    if verbose:
        print(f"  paginas leidas: {len(paginas)} ({sum(len(p.texto) for p in paginas)} chars)")

    llamadas_antes = getattr(cliente, "llamadas_reales", 0) if cliente else 0
    hallazgos = extraer(
        municipio, id_municipio, paginas, cliente, fecha, urls_tipificadas
    )
    llamadas = (getattr(cliente, "llamadas_reales", 0) if cliente else 0) - llamadas_antes

    return MunicipioExtraccion(
        municipio=municipio,
        id_municipio=id_municipio,
        fecha=fecha,
        paginas_leidas=len(paginas),
        caracteres_analizados=sum(len(p.texto) for p in paginas),
        llamadas_ia=max(0, llamadas),
        hallazgos=hallazgos,
    )


def procesar_todos(
    municipios=None, cliente=None, verbose: bool = True
) -> List[MunicipioExtraccion]:
    """Los 86 municipios, en serie.

    En serie a proposito: el cuello de botella es la cuota de la API, no la CPU.
    Paralelizar solo haria chocar los pedidos contra el limite por minuto.
    """
    municipios = list(municipios if municipios is not None else cargar_municipios())
    resultados: List[MunicipioExtraccion] = []
    inicio = time.perf_counter()

    for i, m in enumerate(municipios, start=1):
        try:
            r = procesar(m.nombre, m.id_municipio, cliente=cliente)
        except CuotaAgotada as exc:
            print(f"\n[CUOTA] {exc}")
            print(f"Se procesaron {len(resultados)} de {len(municipios)}. Se guarda lo hecho.")
            break
        except Exception as exc:
            print(f"  [ERROR] {m.nombre}: {type(exc).__name__}: {exc}")
            continue
        resultados.append(r)
        if verbose:
            print(
                f"  [{i:>2}/{len(municipios)}] {m.nombre:<26} "
                f"{len(r.verificados()):>2}/{len(Variable)} verificadas  "
                f"({(time.perf_counter() - inicio) / 60:.1f} min)",
                flush=True,
            )
    return resultados


# ---------------------------------------------------------------------------
# Persistencia (fusiona por municipio - ADR-0013)
# ---------------------------------------------------------------------------


def _fusionar_con_lo_verificado(con: sqlite3.Connection, r: MunicipioExtraccion) -> list:
    """Un hallazgo ya verificado no se pisa con un vacio.

    El modelo no es determinista: el mismo municipio con las mismas paginas puede
    dar 'si' con cita en una corrida y 'no_verificable' en la siguiente. Sin esta
    regla, cada re-corrida borraba evidencia que ya se habia probado (paso con
    Arrecifes y Adolfo Alsina).

    Es la misma regla de ADR-0013 aplicada a Fase 4: la base no se destruye a si
    misma. Un dato verificado solo lo reemplaza otro dato verificado, y ahi gana
    el nuevo porque es mas fresco.
    """
    previos = {
        fila[0]: fila
        for fila in con.execute(
            f"SELECT {', '.join(COLUMNAS)} FROM hallazgos WHERE id_municipio = ?",
            (r.id_municipio,),
        )
    }
    indice_estado = COLUMNAS.index("estado")

    filas = []
    for h in r.hallazgos:
        nueva = tuple(h.to_row()[c] for c in COLUMNAS)
        vieja = previos.get(h.id)
        if (
            vieja is not None
            and vieja[indice_estado] == EstadoHallazgo.VERIFICADO.value
            and h.estado is not EstadoHallazgo.VERIFICADO
        ):
            filas.append(vieja)  # se conserva la evidencia que ya existia
        else:
            filas.append(nueva)
    return filas


def guardar_sqlite(resultados: Sequence[MunicipioExtraccion], path: Path = SQLITE_86) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        for r in resultados:
            filas = _fusionar_con_lo_verificado(con, r)
            con.execute("DELETE FROM hallazgos WHERE id_municipio = ?", (r.id_municipio,))
            con.executemany(
                f"INSERT INTO hallazgos ({', '.join(COLUMNAS)}) "
                f"VALUES ({', '.join('?' for _ in COLUMNAS)})",
                filas,
            )
            con.execute(
                "INSERT OR REPLACE INTO municipios_extraccion "
                "(id_municipio, municipio, fecha, paginas_leidas, caracteres_analizados, "
                " llamadas_ia, verificados, citas_rechazadas) VALUES (?,?,?,?,?,?,?,?)",
                (
                    r.id_municipio, r.municipio, r.fecha, r.paginas_leidas,
                    r.caracteres_analizados, r.llamadas_ia,
                    len(r.verificados()), len(r.rechazados()),
                ),
            )
        con.commit()
    finally:
        con.close()
    return path


def guardar_json(resultados: Sequence[MunicipioExtraccion], path: Path = JSON_86) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    por_id = {}
    if path.exists():
        try:
            for m in json.loads(path.read_text(encoding="utf-8")).get("municipios", []):
                por_id[m["id_municipio"]] = m
        except (OSError, json.JSONDecodeError, KeyError):
            por_id = {}
    for r in resultados:
        por_id[r.id_municipio] = r.model_dump(mode="json")

    municipios = sorted(por_id.values(), key=lambda m: m["id_municipio"])
    path.write_text(
        json.dumps(
            {"total_municipios": len(municipios), "municipios": municipios},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resumen(r: MunicipioExtraccion) -> str:
    lineas = [
        f"{r.municipio} [{r.id_municipio}] - {r.paginas_leidas} paginas, "
        f"{len(r.verificados())}/{len(Variable)} variables con evidencia"
    ]
    for h in r.hallazgos:
        marca = {"verificado": "OK ", "no_verificable": "-- ", "cita_rechazada": "!! "}[
            h.estado.value
        ]
        lineas.append(f"  {marca}{h.variable.value:<26} {h.valor:<16} [{h.confianza.value}]")
        if h.fragmento:
            lineas.append(f'       cita: "{h.fragmento[:96]}"')
            lineas.append(f"       {h.url}")
        if h.detalle:
            lineas.append(f"       detalle: {h.detalle[:96]}")
    if r.rechazados():
        lineas.append(
            f"  {len(r.rechazados())} cita(s) rechazadas: el modelo las invento "
            f"y la verificacion las tumbo (ADR-0014)"
        )
    return "\n".join(lineas)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIP Fase 4 - Extraccion verificada")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--municipio", help="Nombre del municipio (ej: Navarro)")
    grupo.add_argument("--all", action="store_true", help="Los 86 municipios")
    parser.add_argument("--limite", type=int, help="Procesar solo los primeros N")
    parser.add_argument(
        "--reanudar",
        action="store_true",
        help="Saltear los municipios que ya tienen hallazgos y seguir desde ahi",
    )
    parser.add_argument("--sin-ia", action="store_true", help="Solo leer paginas, sin llamar a Gemini")
    parser.add_argument("--sin-cache", action="store_true", help="Ignorar el cache de IA")
    parser.add_argument("--json", type=Path, default=JSON_86)
    parser.add_argument("--sqlite", type=Path, default=SQLITE_86)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cliente = None if args.sin_ia else ClienteGemini(usar_cache=not args.sin_cache)
    inicio = time.perf_counter()

    if args.municipio:
        resultado = procesar(args.municipio, cliente=cliente, verbose=True)
        print(_resumen(resultado))
        resultados = [resultado]
    else:
        municipios = cargar_municipios()
        if args.reanudar:
            hechos = ya_extraidos(args.sqlite)
            municipios = [m for m in municipios if m.nombre not in hechos]
            print(f"Reanudando: {len(hechos)} ya extraidos, quedan {len(municipios)}")
            if not municipios:
                print("Nada pendiente. Los 86 ya tienen hallazgos.")
                return 0
        if args.limite:
            municipios = municipios[: args.limite]
        restantes = cliente.limitador.restantes_hoy() if cliente else 0
        if cliente:
            print(f"Cuota disponible hoy: {restantes} llamadas para {len(municipios)} municipios\n")
        resultados = procesar_todos(municipios, cliente=cliente)
        verificados = sum(len(r.verificados()) for r in resultados)
        rechazadas = sum(len(r.rechazados()) for r in resultados)
        print(
            f"\n{'=' * 68}\n"
            f"Municipios procesados : {len(resultados)}\n"
            f"Variables verificadas : {verificados} de {len(resultados) * len(Variable)}\n"
            f"Citas rechazadas      : {rechazadas}\n"
            f"{'=' * 68}"
        )

    if cliente:
        print(
            f"\nIA: {cliente.llamadas_reales} llamadas reales, "
            f"{cliente.aciertos_cache} desde cache, "
            f"{cliente.limitador.restantes_hoy()} restantes hoy"
        )

    print(f"\nJSON   -> {guardar_json(resultados, args.json)}")
    print(f"SQLite -> {guardar_sqlite(resultados, args.sqlite)}")
    print(f"Tiempo total: {time.perf_counter() - inicio:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
