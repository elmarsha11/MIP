"""
Contorno de cada partido, para que el mapa del tablero sea el municipio.

Hasta ahora el mapa era una nube de puntos encuadrada por los puntos mismos: el
recuadro salia de donde caian las entidades, no de donde termina el partido. Eso
tiene dos consecuencias y la segunda es la que importa:

  1. Dos municipios con la misma cantidad de entidades se ven del mismo tamano,
     aunque uno tenga diez veces la superficie del otro.
  2. **El encuadre miente sobre la cobertura.** Un partido censado solo en su
     casco urbano llena el recuadro y parece cubierto entero; con el contorno
     real se ve el area vacia, que es justo el dato util.

El `osm_id` de la relacion ya esta guardado para los 86 desde el censo, asi que
no hay que resolver nada: se pide la geometria de esa relacion y listo.

    python src/territorio/limites.py --all
    python src/territorio/limites.py --municipio Chascomus

Necesita red. Los contornos no cambian, asi que se bajan una vez.

Por que se simplifican
----------------------
Un partido bonaerense en OSM son miles de puntos. Los 86 sin simplificar no
entran en el HTML que genera el tablero —que ya pesa 3,8 MB— y ademas no se
verian: a 560 pixeles de ancho, dos vertices separados por 20 metros caen en el
mismo pixel. Se aplica Douglas-Peucker con una tolerancia en grados que a esa
escala es sub-pixel, asi que la silueta es la misma y el archivo entra.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

SQLITE_86 = PROJECT_ROOT / "data" / "processed" / "territorio" / "entidades_86.sqlite"

# Grados. A la escala del tablero (~560 px para un partido de ~0.5 grados) esto
# es menos de un pixel: la silueta no cambia y el peso baja un orden de magnitud.
TOLERANCIA = 0.002

DDL = """
CREATE TABLE IF NOT EXISTS limites (
    municipio TEXT PRIMARY KEY,
    osm_id INTEGER,
    anillos TEXT NOT NULL,
    puntos INTEGER NOT NULL,
    puntos_crudos INTEGER NOT NULL,
    lat_min REAL, lat_max REAL, lon_min REAL, lon_max REAL,
    fecha TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Simplificacion
# ---------------------------------------------------------------------------


def _dist_a_recta(p, a, b) -> float:
    """Distancia perpendicular de p al segmento a-b, en grados."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    return abs(dy * px - dx * py + bx * ay - by * ax) / (dx * dx + dy * dy) ** 0.5


def simplificar(puntos: Sequence[Tuple[float, float]], tolerancia: float = TOLERANCIA):
    """Douglas-Peucker iterativo. Recursivo se desborda con miles de vertices."""
    if len(puntos) < 3:
        return list(puntos)

    conservar = [False] * len(puntos)
    conservar[0] = conservar[-1] = True
    pila = [(0, len(puntos) - 1)]

    while pila:
        ini, fin = pila.pop()
        peor, cual = 0.0, -1
        for i in range(ini + 1, fin):
            d = _dist_a_recta(puntos[i], puntos[ini], puntos[fin])
            if d > peor:
                peor, cual = d, i
        if cual != -1 and peor > tolerancia:
            conservar[cual] = True
            pila += [(ini, cual), (cual, fin)]

    return [p for p, si in zip(puntos, conservar) if si]


# ---------------------------------------------------------------------------
# Overpass
# ---------------------------------------------------------------------------


def _anillos_desde_overpass(osm_id: int) -> List[List[Tuple[float, float]]]:
    """Los anillos exteriores de la relacion, en (lon, lat).

    Overpass devuelve la relacion como una lista de ways sueltos y sin ordenar.
    Se los encadena por extremos: cada way se pega al anillo abierto cuyo final
    coincide con alguno de sus dos extremos, dandolo vuelta si hace falta. Sin
    esto el poligono sale hecho un garabato.
    """
    from osm import consultar

    datos = consultar(f"[out:json][timeout:120];relation({osm_id});out geom;", True)
    if not datos:
        return []

    tramos: List[List[Tuple[float, float]]] = []
    for elemento in datos.get("elements", []):
        for miembro in elemento.get("members", []):
            if miembro.get("role") not in ("outer", "", None):
                continue
            geo = miembro.get("geometry") or []
            if len(geo) >= 2:
                tramos.append([(p["lon"], p["lat"]) for p in geo])

    anillos: List[List[Tuple[float, float]]] = []
    while tramos:
        actual = tramos.pop(0)
        pegado = True
        while pegado and actual[0] != actual[-1]:
            pegado = False
            for i, tramo in enumerate(tramos):
                if tramo[0] == actual[-1]:
                    actual += tramos.pop(i)[1:]
                    pegado = True
                    break
                if tramo[-1] == actual[-1]:
                    actual += list(reversed(tramos.pop(i)))[1:]
                    pegado = True
                    break
        if len(actual) >= 4:
            anillos.append(actual)

    # El partido es el anillo grande; los chicos suelen ser islas o ruido.
    anillos.sort(key=len, reverse=True)
    return anillos[:3]


def bajar(municipio: str, osm_id: int) -> Optional[dict]:
    crudos = _anillos_desde_overpass(osm_id)
    if not crudos:
        return None

    simples = [simplificar(a) for a in crudos]
    simples = [a for a in simples if len(a) >= 4]
    if not simples:
        return None

    todos = [p for a in simples for p in a]
    return {
        "municipio": municipio,
        "osm_id": osm_id,
        "anillos": simples,
        "puntos": len(todos),
        "puntos_crudos": sum(len(a) for a in crudos),
        "lon_min": min(p[0] for p in todos), "lon_max": max(p[0] for p in todos),
        "lat_min": min(p[1] for p in todos), "lat_max": max(p[1] for p in todos),
    }


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------


def guardar(limites: Sequence[dict], path: Path = SQLITE_86) -> Path:
    from datetime import datetime, timezone

    ahora = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        for lim in limites:
            con.execute(
                "INSERT OR REPLACE INTO limites (municipio, osm_id, anillos, puntos, "
                "puntos_crudos, lat_min, lat_max, lon_min, lon_max, fecha) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (lim["municipio"], lim["osm_id"],
                 json.dumps(lim["anillos"], separators=(",", ":")),
                 lim["puntos"], lim["puntos_crudos"],
                 lim["lat_min"], lim["lat_max"], lim["lon_min"], lim["lon_max"], ahora),
            )
        con.commit()
    finally:
        con.close()
    return path


def pendientes(path: Path = SQLITE_86) -> List[Tuple[str, int]]:
    """Municipios con osm_id y sin contorno bajado."""
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        return con.execute(
            "SELECT m.municipio, m.osm_id FROM municipios_territorio m "
            "LEFT JOIN limites l ON l.municipio = m.municipio "
            "WHERE m.osm_id IS NOT NULL AND l.municipio IS NULL "
            "ORDER BY m.municipio"
        ).fetchall()
    finally:
        con.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--municipio")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--estado", action="store_true", help="cuantos faltan")
    args = parser.parse_args(argv)

    if args.estado:
        faltan = pendientes()
        print(f"Contornos pendientes: {len(faltan)}")
        for m, _ in faltan[:10]:
            print(f"   {m}")
        return 0

    con = sqlite3.connect(SQLITE_86)
    try:
        if args.municipio:
            fila = con.execute(
                "SELECT municipio, osm_id FROM municipios_territorio WHERE municipio = ?",
                (args.municipio,),
            ).fetchone()
            objetivo = [fila] if fila and fila[1] else []
        elif args.all:
            objetivo = pendientes()
        else:
            parser.error("elegi --municipio, --all o --estado")
            return 2
    finally:
        con.close()

    if not objetivo:
        print("Nada que bajar.")
        return 0

    listos = []
    for i, (municipio, osm_id) in enumerate(objetivo, 1):
        lim = bajar(municipio, osm_id)
        if lim:
            listos.append(lim)
            reduccion = 100 - lim["puntos"] * 100 // max(lim["puntos_crudos"], 1)
            print(f"[{i}/{len(objetivo)}] {municipio}: {lim['puntos']} puntos "
                  f"(de {lim['puntos_crudos']}, -{reduccion}%)")
        else:
            # Sin contorno el mapa sigue andando con el recuadro de los puntos.
            print(f"[{i}/{len(objetivo)}] {municipio}: sin geometria (se omite)")

    if listos:
        guardar(listos)
    print(f"\nGuardados {len(listos)} contornos de {len(objetivo)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
