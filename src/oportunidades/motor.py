"""
Motor comercial: de la evidencia a la lista de lo que UDS puede vender.

    Fase 3 encontro DONDE mirar. Fase 4 reporto QUE DICEN los portales.
    Esto responde QUE LE FALTA a cada municipio y que le vende UDS.

Escribe en su propia base. NUNCA toca hallazgos_86.sqlite: la evidencia de Fase 4
es el activo y no se mezcla con interpretacion comercial.

Uso:
    python src/oportunidades/motor.py --municipio Navarro
    python src/oportunidades/motor.py --all
    python src/oportunidades/motor.py --ficha Navarro      # lectura humana
    python src/oportunidades/motor.py --ranking            # los 86 por potencial
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Optional

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
PROJECT_ROOT = _SRC.parent
for _ruta in (_AQUI, _SRC, _SRC / "extraction", _SRC / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from discovery_engine import buscar_municipio, cargar_municipios  # noqa: E402
from schemas import ahora_iso  # noqa: E402

from catalogo import Area, Friccion  # noqa: E402
from detector import detectar  # noqa: E402
from comercial import MunicipioOportunidades, PESO_FRICCION  # noqa: E402
from paginas import obtener_paginas  # noqa: E402

from llm import crear_proveedor, CuotaAgotada  # noqa: E402

DIR_SALIDA = PROJECT_ROOT / "data" / "processed" / "oportunidades"
SQLITE_OPORTUNIDADES = DIR_SALIDA / "oportunidades_86.sqlite"

DDL = """
CREATE TABLE IF NOT EXISTS oportunidades (
    id TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    area TEXT NOT NULL,
    problema TEXT NOT NULL,
    friccion TEXT NOT NULL CHECK(friccion IN ('alta','media','baja')),
    cita TEXT NOT NULL,
    url TEXT NOT NULL,
    producto TEXT NOT NULL,
    fecha TEXT NOT NULL,
    modelo TEXT
);
CREATE INDEX IF NOT EXISTS idx_op_municipio ON oportunidades(municipio);
CREATE INDEX IF NOT EXISTS idx_op_area ON oportunidades(area);

CREATE TABLE IF NOT EXISTS municipios_oportunidades (
    id_municipio TEXT PRIMARY KEY,
    municipio TEXT NOT NULL UNIQUE,
    fecha TEXT NOT NULL,
    paginas_leidas INTEGER NOT NULL,
    caracteres_analizados INTEGER NOT NULL,
    oportunidades INTEGER NOT NULL,
    citas_rechazadas INTEGER NOT NULL,
    puntaje INTEGER NOT NULL
);
"""

COLUMNAS = (
    "id", "municipio", "id_municipio", "area", "problema", "friccion",
    "cita", "url", "producto", "fecha", "modelo",
)


def procesar(
    municipio: str,
    id_municipio: Optional[str] = None,
    cliente=None,
    usar_cache: bool = True,
    verbose: bool = False,
) -> MunicipioOportunidades:
    if id_municipio is None:
        registro = buscar_municipio(municipio)
        municipio, id_municipio = registro.nombre, registro.id_municipio

    fecha = ahora_iso()
    paginas = obtener_paginas(municipio, id_municipio, usar_cache=usar_cache)
    if verbose:
        print(f"  paginas: {len(paginas)} ({sum(len(p.texto) for p in paginas)} chars)")

    oportunidades, rechazadas = detectar(
        municipio, id_municipio, paginas, cliente, fecha
    )

    return MunicipioOportunidades(
        municipio=municipio,
        id_municipio=id_municipio,
        fecha=fecha,
        paginas_leidas=len(paginas),
        caracteres_analizados=sum(len(p.texto) for p in paginas),
        oportunidades=oportunidades,
        citas_rechazadas=rechazadas,
    )


def procesar_todos(municipios=None, cliente=None, verbose: bool = True) -> List:
    municipios = list(municipios if municipios is not None else cargar_municipios())
    resultados = []
    inicio = time.perf_counter()

    for i, m in enumerate(municipios, start=1):
        try:
            r = procesar(m.nombre, m.id_municipio, cliente=cliente)
        except CuotaAgotada as exc:
            print(f"\n[CUOTA] {exc}")
            print(f"Procesados {len(resultados)} de {len(municipios)}. Se guarda lo hecho.")
            break
        except Exception as exc:
            print(f"  [ERROR] {m.nombre}: {type(exc).__name__}: {exc}")
            continue
        resultados.append(r)
        if verbose:
            print(
                f"  [{i:>2}/{len(municipios)}] {m.nombre:<26} "
                f"{len(r.oportunidades):>2} oportunidades  "
                f"puntaje {r.puntaje():>2}  "
                f"({(time.perf_counter() - inicio) / 60:.1f} min)",
                flush=True,
            )
    return resultados


def guardar(resultados, path: Path = SQLITE_OPORTUNIDADES) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        for r in resultados:
            # Se reemplaza el municipio entero: la lectura comercial es una foto,
            # no un acumulado. Distinto de Fase 4, donde un verificado no se pisa
            # (ADR-0013) porque ahi lo que se guarda es evidencia.
            con.execute(
                "DELETE FROM oportunidades WHERE id_municipio = ?", (r.id_municipio,)
            )
            con.executemany(
                f"INSERT OR REPLACE INTO oportunidades ({', '.join(COLUMNAS)}) "
                f"VALUES ({', '.join('?' for _ in COLUMNAS)})",
                [tuple(o.to_row()[c] for c in COLUMNAS) for o in r.oportunidades],
            )
            con.execute(
                "INSERT OR REPLACE INTO municipios_oportunidades "
                "(id_municipio, municipio, fecha, paginas_leidas, caracteres_analizados,"
                " oportunidades, citas_rechazadas, puntaje) VALUES (?,?,?,?,?,?,?,?)",
                (
                    r.id_municipio, r.municipio, r.fecha, r.paginas_leidas,
                    r.caracteres_analizados, len(r.oportunidades),
                    r.citas_rechazadas, r.puntaje(),
                ),
            )
        con.commit()
    finally:
        con.close()
    return path


# ---------------------------------------------------------------------------
# Lectura humana
# ---------------------------------------------------------------------------

_ORDEN = {Friccion.ALTA: 0, Friccion.MEDIA: 1, Friccion.BAJA: 2}


def ficha(municipio: str, path: Path = SQLITE_OPORTUNIDADES) -> str:
    """La ficha comercial: que le vendo a este municipio y con que prueba."""
    if not Path(path).exists():
        return f"No hay analisis todavia. Core: python src/oportunidades/motor.py --municipio {municipio}"
    con = sqlite3.connect(path)
    try:
        filas = con.execute(
            "SELECT area, producto, problema, friccion, cita, url FROM oportunidades "
            "WHERE municipio = ? ",
            (municipio,),
        ).fetchall()
    finally:
        con.close()

    if not filas:
        return f"{municipio}: sin oportunidades detectadas (o todavia sin analizar)."

    filas.sort(key=lambda f: _ORDEN[Friccion(f[3])])
    puntaje = sum(PESO_FRICCION[Friccion(f[3])] for f in filas)

    lineas = [
        "=" * 74,
        f"{municipio.upper()}  -  {len(filas)} oportunidades, potencial {puntaje}",
        "=" * 74,
    ]
    for area, producto, problema, friccion, cita, url in filas:
        lineas += [
            "",
            f"[{friccion.upper():<5}] {area}  ->  {producto}",
            f"  Situacion hoy: {problema}",
            f'  Prueba: "{cita[:200]}"',
            f"  {url}",
        ]
    lineas += ["", "-" * 74, "Cada linea tiene su cita literal verificada contra la pagina."]
    return "\n".join(lineas)


def ranking(path: Path = SQLITE_OPORTUNIDADES, limite: int = 30) -> str:
    if not Path(path).exists():
        return "No hay analisis todavia. Core: python src/oportunidades/motor.py --all"
    con = sqlite3.connect(path)
    try:
        filas = con.execute(
            "SELECT municipio, oportunidades, puntaje FROM municipios_oportunidades "
            "WHERE oportunidades > 0 ORDER BY puntaje DESC, oportunidades DESC LIMIT ?",
            (limite,),
        ).fetchall()
        por_area = con.execute(
            "SELECT area, producto, COUNT(*) FROM oportunidades GROUP BY area "
            "ORDER BY 3 DESC"
        ).fetchall()
    finally:
        con.close()

    lineas = ["MUNICIPIOS POR POTENCIAL COMERCIAL", "=" * 60,
              f"{'municipio':<28}{'oport.':>8}{'potencial':>11}", "-" * 60]
    lineas += [f"{m:<28}{n:>8}{p:>11}" for m, n, p in filas]
    lineas += ["", "MERCADO POR PRODUCTO", "=" * 60]
    lineas += [f"{a:<20}{prod:<32}{n:>4} municipios" for a, prod, n in por_area]
    return "\n".join(lineas)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIP - Motor comercial (oportunidades UDS)")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--municipio", help="Analizar un municipio")
    grupo.add_argument("--all", action="store_true", help="Los 86")
    grupo.add_argument("--ficha", metavar="MUNICIPIO", help="Ficha comercial (no llama a la IA)")
    grupo.add_argument("--ranking", action="store_true", help="Los 86 por potencial (no llama a la IA)")
    parser.add_argument("--limite", type=int, help="Solo los primeros N municipios")
    parser.add_argument("--sin-cache", action="store_true", help="Volver a descargar las paginas")
    parser.add_argument("--sqlite", type=Path, default=SQLITE_OPORTUNIDADES)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.ficha:
        print(ficha(args.ficha, args.sqlite))
        return 0
    if args.ranking:
        print(ranking(args.sqlite))
        return 0

    # La lectura comercial es interpretacion sobre evidencia ya probada, no
    # sourcing: es barata de re-correr y por eso corre con DeepSeek, que no
    # tiene el techo diario de Gemini. Fase 4 sigue siendo de Gemini.
    cliente = crear_proveedor("deepseek")
    inicio = time.perf_counter()

    if args.municipio:
        r = procesar(args.municipio, cliente=cliente, usar_cache=not args.sin_cache, verbose=True)
        resultados = [r]
        print(f"\n{len(r.oportunidades)} oportunidades, {r.citas_rechazadas} citas rechazadas")
    else:
        municipios = cargar_municipios()
        if args.limite:
            municipios = municipios[: args.limite]
        resultados = procesar_todos(municipios, cliente=cliente)

    guardar(resultados, args.sqlite)
    total = sum(len(r.oportunidades) for r in resultados)
    print(f"\n{total} oportunidades en {len(resultados)} municipios -> {args.sqlite}")
    print(f"IA: {cliente.llamadas_reales} llamadas, {cliente.aciertos_cache} de cache")
    print(f"Tiempo: {time.perf_counter() - inicio:.1f}s")

    if args.municipio:
        print("\n" + ficha(resultados[0].municipio, args.sqlite))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
