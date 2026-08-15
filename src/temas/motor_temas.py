"""
Motor de temas: rastrea un tema declarado por configuracion sobre los 86.

    Fase 3 encontro DONDE mirar. Fase 4 reporto QUE DICEN los portales sobre
    once variables de gobierno digital. Esto responde una pregunta nueva sobre
    un tema que Fase 4 nunca pregunto, sin tocar su evidencia.

Escribe en su propia base. NUNCA toca hallazgos_86.sqlite.

Uso:
    python src/temas/motor_temas.py --listar-temas
    python src/temas/motor_temas.py --tema ambiental --municipio Navarro
    python src/temas/motor_temas.py --tema ambiental --all
    python src/temas/motor_temas.py --tema ambiental --all --con-prensa
    python src/temas/motor_temas.py --tema ambiental --ficha Navarro
    python src/temas/motor_temas.py --tema ambiental --cobertura
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Sequence

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
PROJECT_ROOT = _SRC.parent
for _ruta in (_AQUI, _SRC, _SRC / "extraction", _SRC / "discovery", _SRC / "seguridad"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from discovery_engine import buscar_municipio, cargar_municipios  # noqa: E402
from schemas import ahora_iso  # noqa: E402

from cosecha import paginas_del_tema  # noqa: E402
from definiciones import TEMAS, ids_temas, tema as buscar_tema  # noqa: E402
from interrogador import (  # noqa: E402
    construir_prompt,
    esquema_respuesta,
    verificar_respuesta,
)
from rastreo import Estado, HallazgoTema, MunicipioTema, Tema  # noqa: E402

DIR_SALIDA = PROJECT_ROOT / "data" / "processed" / "temas"
SQLITE_TEMAS = DIR_SALIDA / "temas_86.sqlite"

DDL = """
CREATE TABLE IF NOT EXISTS hallazgos_tema (
    id TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    tema TEXT NOT NULL,
    subtema TEXT NOT NULL,
    estado TEXT NOT NULL
        CHECK(estado IN ('confirmado','indicio','no_compete','sin_evidencia')),
    resumen TEXT,
    cita TEXT NOT NULL,
    url TEXT NOT NULL,
    tipo_evidencia TEXT NOT NULL
        CHECK(tipo_evidencia IN ('oficial','normativa','prensa')),
    fecha TEXT NOT NULL,
    modelo TEXT
);
CREATE INDEX IF NOT EXISTS idx_ht_municipio ON hallazgos_tema(municipio);
CREATE INDEX IF NOT EXISTS idx_ht_tema ON hallazgos_tema(tema, subtema);

CREATE TABLE IF NOT EXISTS municipios_tema (
    id_municipio TEXT NOT NULL,
    municipio TEXT NOT NULL,
    tema TEXT NOT NULL,
    fecha TEXT NOT NULL,
    paginas_leidas INTEGER NOT NULL,
    hallazgos INTEGER NOT NULL,
    confirmados INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (id_municipio, tema)
);
"""

COLUMNAS = (
    "id", "municipio", "id_municipio", "tema", "subtema", "estado",
    "resumen", "cita", "url", "tipo_evidencia", "fecha", "modelo",
)


# ---------------------------------------------------------------------------
# Rastreo
# ---------------------------------------------------------------------------


def rastrear(
    municipio: str,
    id_municipio: str,
    tema: Tema,
    cliente=None,
    con_prensa: bool = False,
    buscador_prensa=None,
) -> MunicipioTema:
    """Rastrea un tema en un municipio y devuelve lo verificado."""
    resultado = MunicipioTema(
        municipio=municipio, id_municipio=id_municipio, tema=tema.id
    )

    try:
        paginas = paginas_del_tema(
            municipio,
            tema,
            con_prensa=con_prensa,
            buscador_prensa=buscador_prensa,
        )
    except FileNotFoundError as exc:
        resultado.error = str(exc)
        return resultado

    resultado.paginas_leidas = len(paginas)
    if not paginas:
        # Sin fuentes no hay nada que preguntar. No es un error: es un municipio
        # del que Fase 3 no descubrio nada util para este tema (ADR-0009).
        return resultado

    if cliente is None:
        from llm import crear_proveedor

        cliente = crear_proveedor()

    respuesta = cliente.generar_json(
        construir_prompt(municipio, tema, paginas), esquema_respuesta(tema)
    )
    resultado.hallazgos = verificar_respuesta(
        respuesta,
        municipio=municipio,
        id_municipio=id_municipio,
        tema=tema,
        paginas=paginas,
        fecha=ahora_iso(),
        modelo=getattr(cliente, "nombre_modelo", None),
    )
    return resultado


def rastrear_todos(
    tema: Tema,
    municipios: Optional[Sequence] = None,
    cliente=None,
    con_prensa: bool = False,
    buscador_prensa=None,
    verbose: bool = True,
) -> List[MunicipioTema]:
    from llm import CuotaAgotada

    lista = list(municipios if municipios is not None else cargar_municipios())
    resultados: List[MunicipioTema] = []

    for i, m in enumerate(lista, 1):
        nombre = getattr(m, "nombre", str(m))
        id_m = getattr(m, "id_municipio", getattr(m, "id", nombre))
        try:
            r = rastrear(
                nombre, id_m, tema, cliente, con_prensa, buscador_prensa
            )
        except CuotaAgotada:
            if verbose:
                print(f"  cuota agotada en {nombre}: se corta y se guarda lo hecho")
            break

        resultados.append(r)
        if verbose:
            confirmados = sum(1 for h in r.hallazgos if h.estado is Estado.CONFIRMADO)
            print(
                f"[{i}/{len(lista)}] {nombre}: {len(r.hallazgos)} hallazgos "
                f"({confirmados} confirmados) de {r.paginas_leidas} paginas"
            )
    return resultados


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------


def guardar(resultados: Sequence[MunicipioTema], path: Path = SQLITE_TEMAS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        for r in resultados:
            # Se reemplaza lo del municipio para ese tema: una corrida nueva
            # manda sobre la anterior, pero no toca los otros temas.
            con.execute(
                "DELETE FROM hallazgos_tema WHERE id_municipio = ? AND tema = ?",
                (r.id_municipio, r.tema),
            )
            for h in r.hallazgos:
                con.execute(
                    f"INSERT OR REPLACE INTO hallazgos_tema ({','.join(COLUMNAS)}) "
                    f"VALUES ({','.join('?' * len(COLUMNAS))})",
                    (
                        h.id, h.municipio, h.id_municipio, h.tema, h.subtema,
                        h.estado.value, h.resumen, h.cita, h.url,
                        h.tipo_evidencia.value if h.tipo_evidencia else "oficial",
                        h.fecha, h.modelo,
                    ),
                )
            con.execute(
                "INSERT OR REPLACE INTO municipios_tema "
                "(id_municipio, municipio, tema, fecha, paginas_leidas, "
                " hallazgos, confirmados, error) VALUES (?,?,?,?,?,?,?,?)",
                (
                    r.id_municipio, r.municipio, r.tema, ahora_iso(),
                    r.paginas_leidas, len(r.hallazgos),
                    sum(1 for h in r.hallazgos if h.estado is Estado.CONFIRMADO),
                    r.error,
                ),
            )
        con.commit()
    finally:
        con.close()
    return path


def leer(id_tema: str, municipio: str, path: Path = SQLITE_TEMAS) -> List[HallazgoTema]:
    if not Path(path).exists():
        return []
    con = sqlite3.connect(path)
    try:
        filas = con.execute(
            f"SELECT {','.join(COLUMNAS[1:])} FROM hallazgos_tema "
            "WHERE tema = ? AND municipio = ?",
            (id_tema, municipio),
        ).fetchall()
    finally:
        con.close()
    return [HallazgoTema(**dict(zip(COLUMNAS[1:], f))) for f in filas]


# ---------------------------------------------------------------------------
# Lectura humana
# ---------------------------------------------------------------------------

_SIMBOLO = {
    Estado.CONFIRMADO: "[si]",
    Estado.INDICIO: "[indicio]",
    Estado.NO_COMPETE: "[no compete]",
    Estado.SIN_EVIDENCIA: "[sin dato]",
}


def ficha(id_tema: str, municipio: str, path: Path = SQLITE_TEMAS) -> str:
    tema = buscar_tema(id_tema)
    hallazgos = leer(id_tema, municipio, path)
    vista = MunicipioTema(
        municipio=municipio,
        id_municipio=hallazgos[0].id_municipio if hallazgos else "?",
        tema=id_tema,
        hallazgos=hallazgos,
    )

    lineas = [f"{municipio} - {tema.nombre}", "=" * 60]
    for sub in tema.subtemas:
        estado = vista.estado_de(sub.id)
        lineas.append("")
        lineas.append(f"{_SIMBOLO[estado]} {sub.id}")
        propios = vista.por_subtema(sub.id)
        if not propios:
            lineas.append("      sin evidencia encontrada")
            continue
        for h in propios:
            lineas.append(f'      "{h.cita[:150]}"')
            lineas.append(f"        {h.tipo_evidencia.value} - {h.url[:80]}")
            if h.resumen:
                lineas.append(f"        lectura: {h.resumen[:150]}")
    return "\n".join(lineas)


def cobertura(id_tema: str, path: Path = SQLITE_TEMAS) -> str:
    """Cuantos municipios tienen evidencia de cada sub-tema."""
    tema = buscar_tema(id_tema)
    if not Path(path).exists():
        return f"Todavia no hay datos de {id_tema}. Corre --all primero."

    con = sqlite3.connect(path)
    try:
        total = con.execute(
            "SELECT COUNT(*) FROM municipios_tema WHERE tema = ?", (id_tema,)
        ).fetchone()[0]
        filas = con.execute(
            "SELECT subtema, estado, COUNT(DISTINCT municipio) FROM hallazgos_tema "
            "WHERE tema = ? GROUP BY subtema, estado",
            (id_tema,),
        ).fetchall()
    finally:
        con.close()

    conteo = {s.id: {} for s in tema.subtemas}
    for subtema, estado, n in filas:
        conteo.setdefault(subtema, {})[estado] = n

    lineas = [
        f"Cobertura de {tema.nombre} sobre {total} municipios rastreados",
        "=" * 68,
        f"{'sub-tema':<24}{'confirmado':>12}{'indicio':>10}{'no compete':>13}{'sin dato':>10}",
    ]
    for sub in tema.subtemas:
        c = conteo.get(sub.id, {})
        con_algo = sum(c.values())
        lineas.append(
            f"{sub.id:<24}{c.get('confirmado', 0):>12}{c.get('indicio', 0):>10}"
            f"{c.get('no_compete', 0):>13}{max(total - con_algo, 0):>10}"
        )
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _buscador_prensa_real():
    """Envuelve el motor de prensa de src/seguridad para el formato del tema."""
    import prensa as prensa_mod
    from catalogo_medios import por_municipio

    medios_por_muni = por_municipio()

    def buscar(municipio: str, tema: Tema):
        notas = []
        for medio in medios_por_muni.get(municipio, []):
            base = getattr(medio, "url", "") or ""
            api = prensa_mod.api_wordpress(base)
            if not api:
                continue
            for senal in tema.senales[:4]:
                notas += prensa_mod.buscar(
                    getattr(medio, "nombre", base), base, api, tema.id, senal
                )
        return [n for n in notas if prensa_mod.es_del_municipio(n, municipio)]

    return buscar


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tema", help=f"tema a rastrear ({', '.join(ids_temas())})")
    parser.add_argument("--municipio", help="rastrear uno solo")
    parser.add_argument("--all", action="store_true", help="rastrear los 86")
    parser.add_argument("--limite", type=int, help="cortar despues de N municipios")
    parser.add_argument("--con-prensa", action="store_true", dest="con_prensa",
                        help="sumar notas de medios locales (evidencia de indicio)")
    parser.add_argument("--ficha", help="mostrar lo ya rastreado de un municipio")
    parser.add_argument("--cobertura", action="store_true",
                        help="cuantos municipios tienen cada sub-tema")
    parser.add_argument("--listar-temas", action="store_true", dest="listar")
    args = parser.parse_args(argv)

    if args.listar:
        for id_t in ids_temas():
            t = TEMAS[id_t]
            print(f"{t.id:<14} {t.nombre}")
            print(f"{'':<14} {t.descripcion}")
            for s in t.subtemas:
                print(f"{'':<16} - {s.id}")
        return 0

    if not args.tema:
        parser.error("hace falta --tema (o usa --listar-temas)")
    try:
        tema = buscar_tema(args.tema)
    except KeyError as exc:
        parser.error(str(exc))
        return 2

    if args.ficha:
        print(ficha(tema.id, args.ficha))
        return 0

    if args.cobertura:
        print(cobertura(tema.id))
        return 0

    buscador = _buscador_prensa_real() if args.con_prensa else None

    if args.municipio:
        m = buscar_municipio(args.municipio)
        r = rastrear(
            m.nombre, m.id_municipio, tema,
            con_prensa=args.con_prensa, buscador_prensa=buscador,
        )
        guardar([r])
        print(ficha(tema.id, m.nombre))
        return 0

    if args.all:
        municipios = cargar_municipios()
        if args.limite:
            municipios = municipios[: args.limite]
        resultados = rastrear_todos(
            tema, municipios, con_prensa=args.con_prensa, buscador_prensa=buscador
        )
        guardar(resultados)
        print()
        print(cobertura(tema.id))
        return 0

    parser.error("elegi --municipio, --all, --ficha o --cobertura")
    return 2


if __name__ == "__main__":
    sys.exit(main())
