"""
Fase 6 - Motor del censo territorial (CLI).

    python src/territorio/censo.py --municipio Chascomús
    python src/territorio/censo.py --all
    python src/territorio/censo.py --municipio Chascomús --geojson chascomus.geojson

Guarda en data/processed/territorio/entidades_86.sqlite y .json, fusionando por
municipio como el resto de MIP (ADR-0013).
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
for _r in (_AQUI, PROJECT_ROOT / "src" / "discovery"):
    if str(_r) not in sys.path:
        sys.path.insert(0, str(_r))

from discovery_engine import buscar_municipio, cargar_municipios  # noqa: E402
from schemas import ahora_iso  # noqa: E402

from entidades import CAPAS, CensoMunicipio, Entidad, TipoEntidad  # noqa: E402
from osm import OverpassCaido, censar, resolver_limite  # noqa: E402

TERRITORIO_DIR = PROJECT_ROOT / "data" / "processed" / "territorio"
SQLITE_86 = TERRITORIO_DIR / "entidades_86.sqlite"
JSON_86 = TERRITORIO_DIR / "entidades_86.json"

DDL = """
CREATE TABLE IF NOT EXISTS entidades (
    id TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    tipo TEXT NOT NULL,
    nombre TEXT,
    latitud REAL,
    longitud REAL,
    direccion TEXT,
    telefono TEXT,
    web TEXT,
    operador TEXT,
    fuente TEXT NOT NULL,
    id_en_fuente TEXT NOT NULL,
    url_fuente TEXT,
    fecha TEXT NOT NULL,
    etiquetas_crudas TEXT,
    UNIQUE(fuente, id_en_fuente)
);
CREATE INDEX IF NOT EXISTS idx_ent_municipio ON entidades(municipio);
CREATE INDEX IF NOT EXISTS idx_ent_tipo ON entidades(tipo);

CREATE TABLE IF NOT EXISTS municipios_territorio (
    id_municipio TEXT PRIMARY KEY,
    municipio TEXT NOT NULL UNIQUE,
    osm_id INTEGER,
    fecha TEXT NOT NULL,
    total_entidades INTEGER NOT NULL,
    ubicadas INTEGER NOT NULL,
    con_nombre INTEGER NOT NULL
);
"""

COLUMNAS = (
    "id", "municipio", "id_municipio", "tipo", "nombre", "latitud", "longitud",
    "direccion", "telefono", "web", "operador", "fuente", "id_en_fuente",
    "url_fuente", "fecha", "etiquetas_crudas",
)


def censar_municipio(nombre: str, id_municipio: Optional[str] = None,
                     refrescar: bool = False) -> CensoMunicipio:
    if id_municipio is None:
        registro = buscar_municipio(nombre)
        nombre, id_municipio = registro.nombre, registro.id_municipio
    fecha = ahora_iso()
    entidades = censar(nombre, id_municipio, fecha, refrescar=refrescar)
    return CensoMunicipio(
        municipio=nombre,
        id_municipio=id_municipio,
        osm_id=resolver_limite(nombre),
        fecha=fecha,
        entidades=entidades,
    )


def ya_censados(path: Path = SQLITE_86) -> set:
    """Municipios que ya tienen entidades guardadas.

    Overpass es un servicio publico y gratuito que se satura: una corrida de 86
    municipios se corta a la mitad. Sin esto, cada reintento vuelve a pedir los
    que ya estaban y nunca se llega al final — que es exactamente por que el
    censo quedo en 3 de 86 durante dos dias.

    Un municipio censado con CERO entidades no cuenta como hecho: puede ser que
    OSM no tenga nada, pero tambien que la consulta haya vuelto vacia por
    saturacion, y esa diferencia no se puede distinguir desde aca. Se reintenta.
    """
    if not Path(path).exists():
        return set()
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {f[0] for f in con.execute("SELECT municipio FROM entidades GROUP BY municipio")}
    except sqlite3.Error:
        return set()
    finally:
        con.close()


def guardar_sqlite(censos: Sequence[CensoMunicipio], path: Path = SQLITE_86) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        for c in censos:
            con.execute("DELETE FROM entidades WHERE id_municipio = ?", (c.id_municipio,))
            con.executemany(
                f"INSERT OR REPLACE INTO entidades ({', '.join(COLUMNAS)}) "
                f"VALUES ({', '.join('?' for _ in COLUMNAS)})",
                [tuple(e.to_row()[k] for k in COLUMNAS) for e in c.entidades],
            )
            r = c.resumen()
            con.execute(
                "INSERT OR REPLACE INTO municipios_territorio "
                "(id_municipio, municipio, osm_id, fecha, total_entidades, ubicadas, con_nombre) "
                "VALUES (?,?,?,?,?,?,?)",
                (c.id_municipio, c.municipio, c.osm_id, c.fecha,
                 r["total"], r["ubicadas"], r["con_nombre"]),
            )
        con.commit()
    finally:
        con.close()
    return path


def guardar_json(censos: Sequence[CensoMunicipio], path: Path = JSON_86) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    por_id = {}
    if path.exists():
        try:
            for m in json.loads(path.read_text(encoding="utf-8")).get("municipios", []):
                por_id[m["id_municipio"]] = m
        except (OSError, json.JSONDecodeError, KeyError):
            por_id = {}
    for c in censos:
        por_id[c.id_municipio] = c.model_dump(mode="json")
    municipios = sorted(por_id.values(), key=lambda m: m["id_municipio"])
    path.write_text(
        json.dumps({"total_municipios": len(municipios), "municipios": municipios},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def a_geojson(censo: CensoMunicipio) -> dict:
    """GeoJSON estandar: se abre en QGIS, Google Earth o cualquier visor de mapas."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [e.longitud, e.latitud]},
                "properties": {
                    "nombre": e.nombre, "tipo": e.tipo.value, "direccion": e.direccion,
                    "telefono": e.telefono, "web": e.web, "operador": e.operador,
                    "fuente": e.url_fuente, "municipio": e.municipio,
                },
            }
            for e in censo.entidades
            if e.ubicada
        ],
    }


def _informe(censo: CensoMunicipio) -> str:
    r = censo.resumen()
    lineas = [
        "",
        "=" * 74,
        f"CENSO TERRITORIAL — {censo.municipio} [{censo.id_municipio}]",
        "=" * 74,
        f"{r['total']} entidades · {r['ubicadas']} con coordenadas · {r['con_nombre']} con nombre",
        f"Fuente: OpenStreetMap (relacion {censo.osm_id}) · {censo.fecha}",
        "",
    ]
    for capa, entidades in censo.por_capa().items():
        lineas.append(f"--- {capa} ({len(entidades)})")
        por_tipo: dict = {}
        for e in entidades:
            por_tipo.setdefault(e.tipo, []).append(e)
        for tipo, grupo in sorted(por_tipo.items(), key=lambda x: -len(x[1])):
            lineas.append(f"  {tipo.value} ({len(grupo)})")
            for e in sorted(grupo, key=lambda x: (x.nombre or "zzz"))[:8]:
                sitio = f" · {e.direccion}" if e.direccion else ""
                lineas.append(f"      {(e.nombre or '(sin nombre)')[:52]}{sitio}")
            if len(grupo) > 8:
                lineas.append(f"      … y {len(grupo) - 8} más")
        lineas.append("")
    lineas.append(
        "OSM es colaborativo: la cobertura varía por municipio y puede estar "
        "incompleta.\nCada entidad trae su URL en openstreetmap.org para verificarla."
    )
    lineas.append("=" * 74)
    return "\n".join(lineas)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIP Fase 6 - Censo territorial")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--municipio")
    grupo.add_argument("--all", action="store_true")
    parser.add_argument("--limite", type=int)
    parser.add_argument(
        "--reanudar",
        action="store_true",
        help="Saltear los municipios ya censados y seguir desde ahi",
    )
    parser.add_argument("--refrescar", action="store_true", help="Ignorar el cache de OSM")
    parser.add_argument("--geojson", type=Path, help="Exportar a GeoJSON")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    inicio = time.perf_counter()
    if args.municipio:
        censo = censar_municipio(args.municipio, refrescar=args.refrescar)
        print(_informe(censo))
        censos = [censo]
        if args.geojson:
            args.geojson.parent.mkdir(parents=True, exist_ok=True)
            args.geojson.write_text(
                json.dumps(a_geojson(censo), ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"\nGeoJSON -> {args.geojson}")
    else:
        municipios = cargar_municipios()
        if args.reanudar:
            hechos = ya_censados()
            municipios = [m for m in municipios if m.nombre not in hechos]
            print(f"Reanudando: {len(hechos)} ya censados, quedan {len(municipios)}.")
            if not municipios:
                print("Nada pendiente. Los 86 estan censados.")
                return 0
        if args.limite:
            municipios = municipios[: args.limite]
        print(f"Censando {len(municipios)} municipios. Overpass es gratuito: "
              f"una consulta cada {6}s, ~{len(municipios) * 8 / 60:.0f} min.\n")
        censos = []
        for i, m in enumerate(municipios, start=1):
            try:
                c = censar_municipio(m.nombre, m.id_municipio, refrescar=args.refrescar)
            except OverpassCaido as exc:
                print(f"  [{i}/{len(municipios)}] {m.nombre}: {exc}. Se guarda lo hecho.")
                break
            except Exception as exc:
                print(f"  [{i}/{len(municipios)}] {m.nombre}: {type(exc).__name__}: {exc}")
                continue
            censos.append(c)
            # Se guarda municipio por municipio, no al final. Guardar solo al
            # final significa que si el proceso muere —timeout, corte de red, un
            # Ctrl+C— se pierden horas de consultas a un servicio que ademas
            # limita el ritmo. Con esto, lo que entro queda, y --reanudar sigue.
            guardar_sqlite([c])
            r = c.resumen()
            print(f"  [{i:>2}/{len(municipios)}] {m.nombre:<26} {r['total']:>4} entidades "
                  f"({r['ubicadas']} ubicadas)", flush=True)

    if censos:
        print(f"\nJSON   -> {guardar_json(censos)}")
        print(f"SQLite -> {guardar_sqlite(censos)}")
    print(f"Tiempo: {time.perf_counter() - inicio:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
