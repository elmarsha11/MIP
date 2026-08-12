"""
Motor de medios: resuelve la semilla a URLs y guarda el catalogo.

Uso:
    python src/medios/motor_medios.py --resolver          # todos, con cache
    python src/medios/motor_medios.py --resolver --limite 10
    python src/medios/motor_medios.py --catalogo          # lo ya resuelto
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
for _ruta in (_AQUI, PROJECT_ROOT / "src" / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

import catalogo_medios  # noqa: E402
from resolver import resolver  # noqa: E402

SALIDA_DIR = PROJECT_ROOT / "data" / "processed" / "medios"
SQLITE = SALIDA_DIR / "medios_86.sqlite"
CACHE = SALIDA_DIR / "cache" / "urls_resueltas.json"

DDL = """
CREATE TABLE IF NOT EXISTS medios (
    nombre TEXT NOT NULL,
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK(tipo IN ('oficial','alternativo')),
    url TEXT,
    titulo TEXT,
    motivo TEXT NOT NULL,
    PRIMARY KEY (nombre, municipio)
);
CREATE INDEX IF NOT EXISTS idx_med_municipio ON medios(municipio);
"""


def _cache_leer() -> Dict[str, dict]:
    if not CACHE.exists():
        return {}
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _cache_escribir(datos: Dict[str, dict]) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def sitios_oficiales() -> Dict[str, dict]:
    """El sitio oficial de cada municipio, de Fase 3.

    Los medios "oficiales" de la semilla son la Municipalidad, y MIP ya tiene
    esos sitios acreditados con evidencia desde Fase 3: 85 de 86. Resolverlos
    otra vez por patrones de dominio era gastar consultas para conseguir peor
    dato — de hecho daba 0 de 88, porque "Municipalidad de Chascomús" no genera
    un dominio plausible.
    """
    ruta = PROJECT_ROOT / "data" / "processed" / "discovery" / "discovery_urls_86.sqlite"
    if not ruta.exists():
        return {}
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        filas = con.execute(
            "SELECT municipio, url, titulo_fragmento FROM discovery_urls "
            "WHERE es_oficial = 1 AND tipo = 'sitio_oficial' "
            "GROUP BY municipio"
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        con.close()
    return {m: {"url": u, "titulo": t} for m, u, t in filas}


def resolver_todos(limite: Optional[int] = None, verbose: bool = True) -> List[dict]:
    """Resuelve cada medio distinto una sola vez.

    Un medio regional cubre varios municipios pero tiene UNA url: resolverlo por
    municipio gastaria una consulta por cada uno para el mismo resultado.

    **Solo se cachea el acierto.** Un fallo puede ser el sitio caido en ese
    momento; guardarlo dejaria al medio sin URL para siempre.
    """
    medios = catalogo_medios.leer()
    cache = _cache_leer()

    nombres = []
    for m in medios:
        if m.nombre not in nombres:
            nombres.append(m.nombre)
    pendientes = [n for n in nombres if n not in cache]
    if limite:
        pendientes = pendientes[:limite]

    if verbose:
        print(f"{len(nombres)} medios distintos, {len(cache)} ya resueltos, "
              f"{len(pendientes)} por resolver\n")

    inicio = time.perf_counter()
    for i, nombre in enumerate(pendientes, start=1):
        r = resolver(nombre)
        if r.url:
            cache[nombre] = {"url": r.url, "titulo": r.titulo, "motivo": r.motivo}
            _cache_escribir(cache)
        if verbose:
            marca = "OK " if r.url else "-- "
            print(f"  [{i:>3}/{len(pendientes)}] {marca}{nombre:<38} "
                  f"{(r.url or r.motivo)[:44]}  ({(time.perf_counter()-inicio)/60:.1f} min)",
                  flush=True)

    oficiales = sitios_oficiales()

    filas = []
    for m in medios:
        if m.tipo == "oficial":
            # El sitio del municipio ya esta acreditado por Fase 3, con evidencia.
            hit = oficiales.get(m.municipio)
            motivo = "sitio oficial acreditado en Fase 3" if hit else "sin sitio oficial en Fase 3"
        else:
            hit = cache.get(m.nombre)
            motivo = hit["motivo"] if hit else "sin resolver"
        filas.append({
            "nombre": m.nombre, "municipio": m.municipio,
            "id_municipio": m.id_municipio, "tipo": m.tipo,
            "url": hit["url"] if hit else None,
            "titulo": hit["titulo"] if hit else None,
            "motivo": motivo,
        })
    return filas


def guardar(filas: List[dict], path: Path = SQLITE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        con.executemany(
            "INSERT OR REPLACE INTO medios "
            "(nombre, municipio, id_municipio, tipo, url, titulo, motivo) "
            "VALUES (:nombre,:municipio,:id_municipio,:tipo,:url,:titulo,:motivo)",
            filas,
        )
        con.commit()
    finally:
        con.close()
    return path


def catalogo(path: Path = SQLITE) -> str:
    if not Path(path).exists():
        return "Sin resolver. Core: python src/medios/motor_medios.py --resolver"
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        total = con.execute("SELECT COUNT(DISTINCT nombre) FROM medios").fetchone()[0]
        con_url = con.execute(
            "SELECT COUNT(DISTINCT nombre) FROM medios WHERE url IS NOT NULL"
        ).fetchone()[0]
        alt = con.execute(
            "SELECT COUNT(DISTINCT nombre) FROM medios WHERE tipo='alternativo'"
        ).fetchone()[0]
        alt_url = con.execute(
            "SELECT COUNT(DISTINCT nombre) FROM medios "
            "WHERE tipo='alternativo' AND url IS NOT NULL"
        ).fetchone()[0]
        sin_ninguno = con.execute(
            "SELECT municipio FROM medios GROUP BY municipio "
            "HAVING SUM(CASE WHEN url IS NOT NULL AND tipo='alternativo' THEN 1 ELSE 0 END) = 0 "
            "ORDER BY municipio"
        ).fetchall()
    finally:
        con.close()
    return "\n".join([
        "CATALOGO DE MEDIOS",
        "=" * 62,
        f"medios distintos          : {total}",
        f"  con URL resuelta        : {con_url}",
        f"alternativos distintos    : {alt}",
        f"  con URL resuelta        : {alt_url}",
        "",
        f"municipios sin NINGUN medio alternativo con URL: {len(sin_ninguno)}",
        "  " + ", ".join(m[0] for m in sin_ninguno) if sin_ninguno else "  ninguno",
        "",
        "Un medio sin URL no es un medio que no existe: es uno que los patrones",
        "de dominio no encontraron. Se declara y se completa a mano.",
    ])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIP - Catalogo de medios locales")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--resolver", action="store_true")
    grupo.add_argument("--catalogo", action="store_true")
    parser.add_argument("--limite", type=int)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.catalogo:
        print(catalogo())
        return 0

    filas = resolver_todos(args.limite)
    guardar(filas)
    print()
    print(catalogo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
