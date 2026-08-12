"""
Segundo eje de seguridad: que tiene y como opera cada municipio.

    src/seguridad/motor_seguridad.py responde CUANTO delito se denuncia (SNIC).
    Esto responde QUE HACE el municipio, leyendo su prensa local.

Uso:
    python src/seguridad/motor_prensa.py --municipio Chascomus
    python src/seguridad/motor_prensa.py --all
    python src/seguridad/motor_prensa.py --ficha Chascomus     # no llama a la IA
    python src/seguridad/motor_prensa.py --cobertura           # no llama a la IA
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
PROJECT_ROOT = _SRC.parent
for _ruta in (_AQUI, _SRC, _SRC / "discovery", _SRC / "medios"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from discovery_engine import buscar_municipio, cargar_municipios  # noqa: E402
from schemas import ahora_iso  # noqa: E402

import prensa  # noqa: E402
from operativos import leer  # noqa: E402
from prensa import CONSULTAS, es_del_municipio  # noqa: E402

from llm import crear_proveedor, CuotaAgotada  # noqa: E402

SALIDA_DIR = PROJECT_ROOT / "data" / "processed" / "seguridad"
SQLITE = SALIDA_DIR / "operativos_86.sqlite"
SQLITE_MEDIOS = PROJECT_ROOT / "data" / "processed" / "medios" / "medios_86.sqlite"

DDL = """
CREATE TABLE IF NOT EXISTS operativos (
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    aspecto TEXT NOT NULL,
    detalle TEXT NOT NULL,
    cita TEXT NOT NULL,
    medio TEXT NOT NULL,
    url TEXT NOT NULL,
    fecha_nota TEXT,
    fecha TEXT NOT NULL,
    modelo TEXT,
    PRIMARY KEY (municipio, aspecto)
);
CREATE TABLE IF NOT EXISTS municipios_operativos (
    municipio TEXT PRIMARY KEY,
    id_municipio TEXT NOT NULL,
    fecha TEXT NOT NULL,
    medios_leidos INTEGER NOT NULL,
    notas_encontradas INTEGER NOT NULL,
    notas_del_municipio INTEGER NOT NULL,
    aspectos INTEGER NOT NULL,
    rechazados INTEGER NOT NULL
);
"""

COLUMNAS = ("municipio", "id_municipio", "aspecto", "detalle", "cita", "medio",
            "url", "fecha_nota", "fecha", "modelo")


def medios_del_municipio(municipio: str) -> List[dict]:
    """Los medios con URL de ese municipio, marcando cuales son regionales.

    Un medio regional cubre varios partidos, y eso cambia como se decide si una
    nota es de este municipio: ver prensa.es_del_municipio.
    """
    if not SQLITE_MEDIOS.exists():
        return []
    con = sqlite3.connect(f"file:{SQLITE_MEDIOS}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        propios = con.execute(
            "SELECT nombre, url FROM medios "
            "WHERE municipio = ? AND tipo = 'alternativo' AND url IS NOT NULL",
            (municipio,),
        ).fetchall()
        cobertura = dict(
            con.execute(
                "SELECT nombre, COUNT(DISTINCT municipio) FROM medios "
                "WHERE tipo = 'alternativo' GROUP BY nombre"
            ).fetchall()
        )
    finally:
        con.close()
    return [
        {"nombre": f["nombre"], "url": f["url"], "regional": cobertura.get(f["nombre"], 1) > 1}
        for f in propios
    ]


def procesar(municipio: str, id_municipio: Optional[str] = None,
             cliente=None, verbose: bool = False) -> dict:
    if id_municipio is None:
        registro = buscar_municipio(municipio)
        municipio, id_municipio = registro.nombre, registro.id_municipio

    fecha = ahora_iso()
    ses = requests.Session()
    medios = medios_del_municipio(municipio)

    todas, propias = [], []
    for m in medios:
        notas = prensa.notas_del_medio(m["nombre"], m["url"], ses)
        todas += notas
        propias += [n for n in notas if es_del_municipio(n, municipio, regional=m["regional"])]

    if verbose:
        print(f"  {len(medios)} medios, {len(todas)} notas, {len(propias)} del municipio")

    aspectos, rechazados = leer(municipio, id_municipio, propias, cliente, fecha)
    return {
        "municipio": municipio, "id_municipio": id_municipio, "fecha": fecha,
        "medios_leidos": len(medios), "notas_encontradas": len(todas),
        "notas_del_municipio": len(propias), "aspectos": aspectos,
        "rechazados": rechazados,
    }


def procesar_todos(municipios=None, cliente=None, verbose: bool = True) -> List[dict]:
    municipios = list(municipios if municipios is not None else cargar_municipios())
    resultados, inicio = [], time.perf_counter()
    for i, m in enumerate(municipios, start=1):
        try:
            r = procesar(m.nombre, m.id_municipio, cliente=cliente)
        except CuotaAgotada as exc:
            print(f"\n[CUOTA] {exc}\nSe guarda lo hecho.")
            break
        except Exception as exc:
            print(f"  [ERROR] {m.nombre}: {type(exc).__name__}: {exc}")
            continue
        resultados.append(r)
        # Se guarda municipio por municipio. Guardar solo al final significa que
        # un corte pierde horas de lectura y de llamadas al modelo: es la leccion
        # que costo el censo territorial, que quedo dos dias en 3 de 86.
        guardar([r])
        if verbose:
            print(f"  [{i:>2}/{len(municipios)}] {m.nombre:<26} "
                  f"{len(r['aspectos'])}/7 aspectos  "
                  f"({r['notas_del_municipio']} notas)  "
                  f"({(time.perf_counter()-inicio)/60:.1f} min)", flush=True)
    return resultados


def guardar(resultados: List[dict], path: Path = SQLITE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        for r in resultados:
            # Foto, no acumulado: un centro de monitoreo que se dejo de nombrar
            # tiene que desaparecer, no quedar de una corrida vieja.
            con.execute("DELETE FROM operativos WHERE municipio = ?", (r["municipio"],))
            con.executemany(
                f"INSERT OR REPLACE INTO operativos ({', '.join(COLUMNAS)}) "
                f"VALUES ({', '.join(':' + c for c in COLUMNAS)})",
                r["aspectos"],
            )
            con.execute(
                "INSERT OR REPLACE INTO municipios_operativos VALUES (?,?,?,?,?,?,?,?)",
                (r["municipio"], r["id_municipio"], r["fecha"], r["medios_leidos"],
                 r["notas_encontradas"], r["notas_del_municipio"],
                 len(r["aspectos"]), r["rechazados"]),
            )
        con.commit()
    finally:
        con.close()
    return path


ETIQUETAS = {
    "patrulla_urbana": "Patrulla urbana / policía local",
    "centro_monitoreo": "Centro de monitoreo / cámaras",
    "policia_bonaerense": "Policía Bonaerense",
    "fuerzas_federales": "Fuerzas federales",
    "allanamientos": "Allanamientos",
    "operativos": "Operativos de control",
    "alarmas_vecinales": "Alarmas vecinales / botón antipánico",
}


def ficha(municipio: str, path: Path = SQLITE) -> str:
    if not Path(path).exists():
        return f"Sin analizar. Core: python src/seguridad/motor_prensa.py --municipio {municipio}"
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        filas = con.execute(
            "SELECT * FROM operativos WHERE municipio = ? ORDER BY aspecto", (municipio,)
        ).fetchall()
        resumen = con.execute(
            "SELECT * FROM municipios_operativos WHERE municipio = ?", (municipio,)
        ).fetchone()
    finally:
        con.close()

    lineas = ["=" * 74, f"{municipio.upper()}  -  cómo opera en seguridad", "=" * 74, ""]
    if resumen:
        lineas.append(
            f"{resumen['medios_leidos']} medios leídos, "
            f"{resumen['notas_del_municipio']} notas del municipio en 12 meses"
        )
        lineas.append("")

    encontrados = {f["aspecto"] for f in filas}
    for aspecto, etiqueta in ETIQUETAS.items():
        if aspecto in encontrados:
            f = next(x for x in filas if x["aspecto"] == aspecto)
            lineas += [
                f"[SI] {etiqueta}",
                f"     {f['detalle']}",
                f'     "{f["cita"][:150]}"',
                f"     {f['medio']} · {f['fecha_nota']} · {f['url']}",
                "",
            ]
        else:
            lineas.append(f"[--] {etiqueta}: sin evidencia en la prensa leída")
    lineas += [
        "",
        "-" * 74,
        "Ausencia de evidencia no es evidencia de ausencia: que la prensa no lo",
        "haya publicado en 12 meses no prueba que el municipio no lo tenga.",
    ]
    return "\n".join(lineas)


def cobertura(path: Path = SQLITE) -> str:
    if not Path(path).exists():
        return "Sin analizar. Core: python src/seguridad/motor_prensa.py --all"
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tot = con.execute("SELECT COUNT(*) FROM municipios_operativos").fetchone()[0]
        con_algo = con.execute("SELECT COUNT(DISTINCT municipio) FROM operativos").fetchone()[0]
        por_aspecto = con.execute(
            "SELECT aspecto, COUNT(*) FROM operativos GROUP BY aspecto ORDER BY 2 DESC"
        ).fetchall()
        sin_notas = con.execute(
            "SELECT COUNT(*) FROM municipios_operativos WHERE notas_del_municipio = 0"
        ).fetchone()[0]
    finally:
        con.close()
    lineas = [
        "CÓMO OPERAN — COBERTURA", "=" * 60,
        f"municipios procesados        : {tot}",
        f"con al menos un aspecto      : {con_algo}",
        f"sin ninguna nota encontrada  : {sin_notas}",
        "", "aspectos verificados:",
    ]
    lineas += [f"   {ETIQUETAS.get(a, a):<40}{n:>4} municipios" for a, n in por_aspecto]
    return "\n".join(lineas)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIP - Seguridad, eje 2 (prensa local)")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--municipio")
    grupo.add_argument("--all", action="store_true")
    grupo.add_argument("--ficha", metavar="MUNICIPIO")
    grupo.add_argument("--cobertura", action="store_true")
    parser.add_argument("--limite", type=int)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.ficha:
        print(ficha(args.ficha))
        return 0
    if args.cobertura:
        print(cobertura())
        return 0

    cliente = crear_proveedor("deepseek")
    inicio = time.perf_counter()

    if args.municipio:
        r = procesar(args.municipio, cliente=cliente, verbose=True)
        resultados = [r]
    else:
        municipios = cargar_municipios()
        if args.limite:
            municipios = municipios[: args.limite]
        resultados = procesar_todos(municipios, cliente=cliente)

    guardar(resultados)
    print(f"\nIA: {cliente.llamadas_reales} llamadas, {cliente.aciertos_cache} de cache")
    print(f"Tiempo: {time.perf_counter() - inicio:.1f}s")
    if args.municipio:
        print()
        print(ficha(resultados[0]["municipio"]))
    else:
        print()
        print(cobertura())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
