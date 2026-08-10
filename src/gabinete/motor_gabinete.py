"""
Motor de gabinete: quien gobierna cada municipio, con el decreto que lo prueba.

    Fase 3 encontro DONDE mirar. Fase 4 reporto QUE DICEN los portales.
    Esto responde QUIEN ESTA A CARGO, que es a quien hay que ir a ver.

Por que no se saca del resumen de un buscador: el 2026-08-09 se comparo el
gabinete que devuelve Google para Chascomus (citando el Instagram municipal)
contra el Boletin Oficial del 16/07/2026. Tres secretarios coincidian y uno no:
el buscador daba Jorge Marino en Obras, el decreto dice Lucas Funes. En ese
boletin "Marino" aparece cero veces y "Funes" once. Un dato asi no se descubre
mirando mas fuerte el resumen: hace falta la fuente.

Uso:
    python src/gabinete/motor_gabinete.py --municipio Chascomus
    python src/gabinete/motor_gabinete.py --all
    python src/gabinete/motor_gabinete.py --ficha Chascomus
    python src/gabinete/motor_gabinete.py --cobertura
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

import sibom  # noqa: E402
from autoridades import Cargo, MunicipioGabinete, TipoFuente  # noqa: E402
from lector import leer  # noqa: E402

from llm import crear_proveedor, CuotaAgotada  # noqa: E402

DIR_SALIDA = PROJECT_ROOT / "data" / "processed" / "gabinete"
SQLITE_GABINETE = DIR_SALIDA / "gabinete_86.sqlite"

DDL = """
CREATE TABLE IF NOT EXISTS autoridades (
    id TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    cargo TEXT NOT NULL CHECK(cargo IN ('intendente','secretario')),
    area TEXT,
    nombre TEXT NOT NULL,
    cita TEXT NOT NULL,
    url TEXT NOT NULL,
    fuente TEXT NOT NULL,
    confianza TEXT NOT NULL,
    fecha TEXT NOT NULL,
    modelo TEXT
);
CREATE INDEX IF NOT EXISTS idx_aut_municipio ON autoridades(municipio);
CREATE INDEX IF NOT EXISTS idx_aut_cargo ON autoridades(cargo);

CREATE TABLE IF NOT EXISTS municipios_gabinete (
    id_municipio TEXT PRIMARY KEY,
    municipio TEXT NOT NULL UNIQUE,
    fecha TEXT NOT NULL,
    boletines_leidos INTEGER NOT NULL,
    caracteres_analizados INTEGER NOT NULL,
    autoridades INTEGER NOT NULL,
    rechazadas INTEGER NOT NULL
);
"""

COLUMNAS = ("id", "municipio", "id_municipio", "cargo", "area", "nombre", "cita",
            "url", "fuente", "confianza", "fecha", "modelo")


def procesar(
    municipio: str,
    id_municipio: Optional[str] = None,
    cliente=None,
    maximo_boletines: int = sibom.BOLETINES_POR_MUNICIPIO,
    verbose: bool = False,
) -> MunicipioGabinete:
    if id_municipio is None:
        registro = buscar_municipio(municipio)
        municipio, id_municipio = registro.nombre, registro.id_municipio

    fecha = ahora_iso()
    fuentes = sibom.boletines(municipio, maximo=maximo_boletines)
    if verbose:
        print(f"  boletines: {len(fuentes)} ({sum(len(f.texto) for f in fuentes)} chars)")

    autoridades, rechazadas = leer(
        municipio, id_municipio, fuentes, cliente, fecha, TipoFuente.BOLETIN_OFICIAL
    )

    return MunicipioGabinete(
        municipio=municipio,
        id_municipio=id_municipio,
        fecha=fecha,
        boletines_leidos=len(fuentes),
        caracteres_analizados=sum(len(f.texto) for f in fuentes),
        autoridades=autoridades,
        rechazadas=rechazadas,
    )


def procesar_todos(municipios=None, cliente=None, verbose: bool = True) -> List:
    municipios = list(municipios if municipios is not None else cargar_municipios())
    resultados, inicio = [], time.perf_counter()

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
            intendente = r.intendente()
            print(
                f"  [{i:>2}/{len(municipios)}] {m.nombre:<26} "
                f"{len(r.secretarios()):>2} secretarios  "
                f"int: {(intendente.nombre if intendente else '-'):<24} "
                f"({(time.perf_counter() - inicio) / 60:.1f} min)",
                flush=True,
            )
    return resultados


def guardar(resultados, path: Path = SQLITE_GABINETE) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        for r in resultados:
            # El gabinete es una foto: se reemplaza el municipio entero. Un
            # secretario que dejo el cargo tiene que DESAPARECER, no quedar
            # conviviendo con el nuevo. Es lo contrario de Fase 4, donde un
            # verificado no se pisa (ADR-0013), porque alla se guarda evidencia
            # de lo que decia el portal y aca el estado de una cosa que cambia.
            con.execute("DELETE FROM autoridades WHERE id_municipio = ?", (r.id_municipio,))
            con.executemany(
                f"INSERT OR REPLACE INTO autoridades ({', '.join(COLUMNAS)}) "
                f"VALUES ({', '.join('?' for _ in COLUMNAS)})",
                [tuple(a.to_row()[c] for c in COLUMNAS) for a in r.autoridades],
            )
            con.execute(
                "INSERT OR REPLACE INTO municipios_gabinete VALUES (?,?,?,?,?,?,?)",
                (r.id_municipio, r.municipio, r.fecha, r.boletines_leidos,
                 r.caracteres_analizados, len(r.autoridades), r.rechazadas),
            )
        con.commit()
    finally:
        con.close()
    return path


def ficha(municipio: str, path: Path = SQLITE_GABINETE) -> str:
    if not Path(path).exists():
        return f"Sin analizar. Core: python src/gabinete/motor_gabinete.py --municipio {municipio}"
    con = sqlite3.connect(path)
    try:
        filas = con.execute(
            "SELECT cargo, area, nombre, cita, url, confianza FROM autoridades "
            "WHERE municipio = ? ORDER BY cargo, area",
            (municipio,),
        ).fetchall()
    finally:
        con.close()
    if not filas:
        return f"{municipio}: sin autoridades detectadas (o todavia sin analizar)."

    lineas = ["=" * 74, f"{municipio.upper()}  -  cupula municipal", "=" * 74]
    for cargo, area, nombre, cita, url, confianza in filas:
        titulo = "INTENDENTE" if cargo == "intendente" else f"Secretaria de {area or '?'}"
        lineas += [
            "",
            f"{titulo}: {nombre}   [{confianza}]",
            f'  Prueba: "{cita[:190]}"',
            f"  {url}",
        ]
    lineas += ["", "-" * 74,
               "Cada nombre sale de una cita literal verificada contra el boletin."]
    return "\n".join(lineas)


def cobertura(path: Path = SQLITE_GABINETE) -> str:
    """Cuanto se cubrio y cuanto falta. El faltante se ve, no se disimula."""
    if not Path(path).exists():
        return "Sin analizar todavia."
    con = sqlite3.connect(path)
    try:
        tot = con.execute("SELECT COUNT(*) FROM municipios_gabinete").fetchone()[0]
        con_int = con.execute(
            "SELECT COUNT(DISTINCT municipio) FROM autoridades WHERE cargo='intendente'"
        ).fetchone()[0]
        con_sec = con.execute(
            "SELECT COUNT(DISTINCT municipio) FROM autoridades WHERE cargo='secretario'"
        ).fetchone()[0]
        secs = con.execute("SELECT COUNT(*) FROM autoridades WHERE cargo='secretario'").fetchone()[0]
        sin_bol = con.execute(
            "SELECT municipio FROM municipios_gabinete WHERE boletines_leidos = 0 ORDER BY municipio"
        ).fetchall()
    finally:
        con.close()
    return "\n".join([
        "COBERTURA DEL GABINETE",
        "=" * 60,
        f"Municipios procesados      : {tot}",
        f"Con intendente identificado: {con_int}",
        f"Con algun secretario       : {con_sec}",
        f"Secretarios totales        : {secs}",
        f"Sin boletin en SIBOM       : {len(sin_bol)}",
        "",
        "Sin boletin (hay que ir por el portal o la red oficial):",
        "  " + ", ".join(m[0] for m in sin_bol) if sin_bol else "  ninguno",
    ])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIP - Cupula municipal desde el Boletin Oficial")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--municipio")
    grupo.add_argument("--all", action="store_true")
    grupo.add_argument("--ficha", metavar="MUNICIPIO", help="No llama a la IA")
    grupo.add_argument("--cobertura", action="store_true", help="No llama a la IA")
    parser.add_argument("--limite", type=int)
    parser.add_argument("--boletines", type=int, default=sibom.BOLETINES_POR_MUNICIPIO)
    parser.add_argument("--sqlite", type=Path, default=SQLITE_GABINETE)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.ficha:
        print(ficha(args.ficha, args.sqlite))
        return 0
    if args.cobertura:
        print(cobertura(args.sqlite))
        return 0

    # DeepSeek: son textos largos pero la pregunta es acotada, y hay que
    # re-correrlo cada vez que cambia un gabinete. El techo diario de Gemini no
    # da para eso. Fase 4 sigue con Gemini.
    cliente = crear_proveedor("deepseek")
    inicio = time.perf_counter()

    if args.municipio:
        r = procesar(args.municipio, cliente=cliente, maximo_boletines=args.boletines,
                     verbose=True)
        resultados = [r]
        print(f"\n{len(r.autoridades)} autoridades, {r.rechazadas} rechazadas")
    else:
        municipios = cargar_municipios()
        if args.limite:
            municipios = municipios[: args.limite]
        resultados = procesar_todos(municipios, cliente=cliente)

    guardar(resultados, args.sqlite)
    print(f"\n{sum(len(r.autoridades) for r in resultados)} autoridades -> {args.sqlite}")
    print(f"IA: {cliente.llamadas_reales} llamadas, {cliente.aciertos_cache} de cache")
    print(f"Tiempo: {time.perf_counter() - inicio:.1f}s")

    if args.municipio:
        print("\n" + ficha(resultados[0].municipio, args.sqlite))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
