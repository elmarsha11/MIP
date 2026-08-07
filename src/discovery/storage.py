"""
Persistencia de Fase 3: JSON + SQLite.

La tabla discovery_urls es literalmente el DDL de schemas/discovery_schema.md.
Se agrega una segunda tabla, municipios_discovery, para poder registrar tambien
los municipios en los que NO se encontro nada: sin ella, un municipio sin URLs
desaparece del archivo y se vuelve indistinguible de uno no procesado. ADR-0009
exige lo contrario: el vacio se ve.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

try:  # ejecutado como paquete
    from .schemas import Confianza, MunicipioDiscovery, TipoURL, es_https
except ImportError:  # ejecutado como script
    from schemas import Confianza, MunicipioDiscovery, TipoURL, es_https  # type: ignore[no-redef]

DDL = """
CREATE TABLE IF NOT EXISTS discovery_urls (
    id TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    url TEXT NOT NULL,
    tipo TEXT NOT NULL,
    fuente_query TEXT,
    titulo_fragmento TEXT,
    fecha_descubrimiento TEXT NOT NULL,
    confianza TEXT NOT NULL CHECK(confianza IN ('Alta','Media','Baja','0%')),
    estado_validacion TEXT NOT NULL,
    es_oficial BOOLEAN,
    UNIQUE(municipio, url)
);

CREATE INDEX IF NOT EXISTS idx_municipio ON discovery_urls(municipio);
CREATE INDEX IF NOT EXISTS idx_tipo ON discovery_urls(tipo);

-- Un registro por municipio procesado, incluidos los que dieron 0 URLs.
CREATE TABLE IF NOT EXISTS municipios_discovery (
    id_municipio TEXT PRIMARY KEY,
    municipio TEXT NOT NULL UNIQUE,
    poblacion INTEGER,
    fecha_descubrimiento TEXT NOT NULL,
    tiempo_ejecucion_segundos REAL,
    total_urls INTEGER NOT NULL,
    urls_con_evidencia INTEGER NOT NULL,
    urls_alta INTEGER NOT NULL,
    tiene_sitio_oficial INTEGER NOT NULL,
    -- 1 = el sitio oficial del municipio no ofrece HTTPS. Es un hallazgo de
    -- madurez digital para Fase 5, no un error del relevamiento (ADR-0012).
    sitio_sin_https INTEGER,
    estado TEXT NOT NULL
);
"""

COLUMNAS = (
    "id", "municipio", "id_municipio", "url", "tipo", "fuente_query",
    "titulo_fragmento", "fecha_descubrimiento", "confianza", "estado_validacion",
    "es_oficial",
)


def sitio_sin_https(resultado: MunicipioDiscovery) -> Optional[int]:
    """1 si el sitio oficial del municipio no ofrece TLS, 0 si lo ofrece,
    None si no se encontro sitio. Hallazgo de madurez digital (ADR-0012)."""
    oficiales = resultado.por_tipo(TipoURL.SITIO_OFICIAL)
    if not oficiales:
        return None
    return 0 if any(es_https(u.url) for u in oficiales) else 1


def estado_municipio(resultado: MunicipioDiscovery) -> str:
    """Resumen honesto del municipio (ADR-0009 / ADR-0010).

    descubierto      : hay sitio oficial con confianza Alta.
    parcial          : hay evidencia pero ningun sitio oficial confirmado.
    no_encontrado    : se ejecuto el pipeline y no aparecio nada verificable.
    """
    if any(
        u.tipo is TipoURL.SITIO_OFICIAL and u.confianza is Confianza.ALTA
        for u in resultado.urls
    ):
        return "descubierto"
    if resultado.con_evidencia():
        return "parcial"
    return "no_encontrado"


def guardar_json(resultados: Sequence[MunicipioDiscovery], path: Path) -> Path:
    """Escribe el JSON fusionando con lo que ya habia, por municipio.

    Fusiona, no pisa: correr solo 3 municipios no puede borrar del archivo a los
    otros 83 que ya estaban relevados. Es la misma semantica que ya tenia el
    SQLite (upsert por municipio) y hace que las corridas parciales sirvan.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    por_municipio: Dict[str, dict] = {}
    if path.exists():
        try:
            previo = json.loads(path.read_text(encoding="utf-8"))
            for m in previo.get("municipios", []):
                por_municipio[m["id_municipio"]] = m
        except (OSError, json.JSONDecodeError, KeyError):
            por_municipio = {}

    for r in resultados:
        por_municipio[r.id_municipio] = {
            **r.model_dump(mode="json"),
            "estado": estado_municipio(r),
        }

    municipios = sorted(por_municipio.values(), key=lambda m: m["id_municipio"])
    payload = {
        "total_municipios": len(municipios),
        "total_urls": sum(m["total_urls"] for m in municipios),
        "municipios": municipios,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# Columnas agregadas despues de la primera version de la tabla. CREATE TABLE
# IF NOT EXISTS no toca una tabla que ya existe, asi que hay que agregarlas a mano.
MIGRACIONES = (
    ("municipios_discovery", "sitio_sin_https", "INTEGER"),
)


def _migrar(con: sqlite3.Connection) -> None:
    for tabla, columna, tipo in MIGRACIONES:
        existentes = {fila[1] for fila in con.execute(f"PRAGMA table_info({tabla})")}
        if existentes and columna not in existentes:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")


def guardar_sqlite(resultados: Sequence[MunicipioDiscovery], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        _migrar(con)
        for r in resultados:
            # Idempotente: re-correr un municipio reemplaza sus filas, no las duplica.
            con.execute("DELETE FROM discovery_urls WHERE municipio = ?", (r.municipio,))
            con.executemany(
                f"INSERT INTO discovery_urls ({', '.join(COLUMNAS)}) "
                f"VALUES ({', '.join('?' for _ in COLUMNAS)})",
                [tuple(u.to_row()[c] for c in COLUMNAS) for u in r.urls],
            )
            con.execute(
                """
                INSERT INTO municipios_discovery
                    (id_municipio, municipio, poblacion, fecha_descubrimiento,
                     tiempo_ejecucion_segundos, total_urls, urls_con_evidencia,
                     urls_alta, tiene_sitio_oficial, sitio_sin_https, estado)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id_municipio) DO UPDATE SET
                    municipio=excluded.municipio,
                    poblacion=excluded.poblacion,
                    fecha_descubrimiento=excluded.fecha_descubrimiento,
                    tiempo_ejecucion_segundos=excluded.tiempo_ejecucion_segundos,
                    total_urls=excluded.total_urls,
                    urls_con_evidencia=excluded.urls_con_evidencia,
                    urls_alta=excluded.urls_alta,
                    tiene_sitio_oficial=excluded.tiene_sitio_oficial,
                    sitio_sin_https=excluded.sitio_sin_https,
                    estado=excluded.estado
                """,
                (
                    r.id_municipio,
                    r.municipio,
                    r.poblacion,
                    r.fecha_descubrimiento,
                    r.tiempo_ejecucion_segundos,
                    r.total_urls,
                    len(r.con_evidencia()),
                    len(r.por_confianza(Confianza.ALTA)),
                    int(bool(r.por_tipo(TipoURL.SITIO_OFICIAL))),
                    sitio_sin_https(r),
                    estado_municipio(r),
                ),
            )
        con.commit()
    finally:
        con.close()
    return path


def guardar(resultados: Sequence[MunicipioDiscovery], json_path: Path, sqlite_path: Path):
    return guardar_json(resultados, json_path), guardar_sqlite(resultados, sqlite_path)


__all__ = ["DDL", "estado_municipio", "guardar", "guardar_json", "guardar_sqlite", "sitio_sin_https"]
