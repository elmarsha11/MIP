"""
Motor de seguridad: cuanto delito denunciado tiene cada municipio.

    Fase 3 encontro DONDE mirar. Fase 4 reporto QUE DICEN los portales.
    src/gabinete responde QUIEN esta a cargo.
    Esto responde CUANTO DELITO SE DENUNCIA, con la fuente oficial.

Es el primero de los dos ejes de seguridad. El segundo —como operan, que
operativos hacen, que fuerzas actuan— no esta en ninguna estadistica y sale de
los medios locales. Este modulo es la linea base contra la cual se leera aquello.

Tres advertencias que viajan con el numero y no se sacan:

  1. **Son denuncias, no delitos.** Dos partidos con el mismo delito real pero
     distinta cultura de denuncia dan distinto.
  2. **El nivel es relativo a los 86**, no absoluto. "Alto" significa "en el
     tercio superior de los municipios relevados", no "peligroso".
  3. **El indice excluye los delitos sin denunciante** (estupefacientes, armas),
     que miden despliegue policial y no victimizacion. Se informan aparte.

Uso:
    python src/seguridad/motor_seguridad.py --todos
    python src/seguridad/motor_seguridad.py --ficha Chascomus
    python src/seguridad/motor_seguridad.py --ranking
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
PROJECT_ROOT = _SRC.parent
for _ruta in (_AQUI, _SRC / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

import snic  # noqa: E402
from indice import (  # noqa: E402
    ACTIVIDAD_POLICIAL,
    CONTRA_LA_INTEGRIDAD_SEXUAL,
    CONTRA_LA_PROPIEDAD,
    CONTRA_LAS_PERSONAS,
    DELITOS_DEL_INDICE,
    EXCLUIDOS,
    POBLACION_ESTACIONAL,
    clasificar,
    cortes_por_terciles,
)

SALIDA_DIR = PROJECT_ROOT / "data" / "processed" / "seguridad"
SQLITE = SALIDA_DIR / "seguridad_86.sqlite"

DDL = """
CREATE TABLE IF NOT EXISTS seguridad (
    municipio TEXT PRIMARY KEY,
    anio INTEGER NOT NULL,
    nivel TEXT NOT NULL CHECK(nivel IN ('bajo','medio','alto')),
    tasa_indice REAL NOT NULL,
    hechos_indice INTEGER NOT NULL,
    tasa_personas REAL, tasa_propiedad REAL, tasa_sexual REAL,
    homicidios INTEGER, tasa_homicidios REAL,
    robos INTEGER, tasa_robos REAL,
    tasa_actividad_policial REAL,
    poblacion_estacional INTEGER NOT NULL DEFAULT 0,
    fuente TEXT NOT NULL
);
"""

COLUMNAS = (
    "municipio", "anio", "nivel", "tasa_indice", "hechos_indice",
    "tasa_personas", "tasa_propiedad", "tasa_sexual",
    "homicidios", "tasa_homicidios", "robos", "tasa_robos",
    "tasa_actividad_policial", "poblacion_estacional", "fuente",
)


def _suma(hechos, delitos) -> tuple:
    """(hechos, tasa) sumados sobre un grupo de delitos.

    Las tasas se pueden sumar porque todas estan calculadas sobre la misma
    poblacion del mismo partido y anio.
    """
    elegidos = [h for h in hechos if h.delito in delitos]
    return sum(h.hechos for h in elegidos), sum(h.tasa for h in elegidos)


def calcular(refrescar: bool = False) -> List[dict]:
    datos = snic.leer(refrescar)
    anio = snic.ultimo_anio(datos)
    if anio is None:
        return []
    faltan = snic.sin_datos_en(datos, anio)
    if faltan:
        # No se rellena ni se los mete con el dato de otro anio: se declara.
        print(f"  [sin dato en {anio}] {', '.join(faltan)}")

    filas = []
    for municipio, hechos in datos.items():
        del_anio = [h for h in hechos if h.anio == anio]
        if not del_anio:
            continue
        hechos_idx, tasa_idx = _suma(del_anio, DELITOS_DEL_INDICE)
        _, tasa_per = _suma(del_anio, CONTRA_LAS_PERSONAS)
        _, tasa_prop = _suma(del_anio, CONTRA_LA_PROPIEDAD)
        _, tasa_sex = _suma(del_anio, CONTRA_LA_INTEGRIDAD_SEXUAL)
        _, tasa_pol = _suma(del_anio, ACTIVIDAD_POLICIAL)
        hom, tasa_hom = _suma(del_anio, ("Homicidios dolosos",))
        rob, tasa_rob = _suma(
            del_anio,
            (
                "Robos (excluye los agravados por el resultado de lesiones y/o muertes)",
                "Robos agravados por el resultado de lesiones y/o muertes",
            ),
        )
        filas.append({
            "municipio": municipio, "anio": anio,
            "tasa_indice": round(tasa_idx, 1), "hechos_indice": hechos_idx,
            "tasa_personas": round(tasa_per, 1),
            "tasa_propiedad": round(tasa_prop, 1),
            "tasa_sexual": round(tasa_sex, 1),
            "homicidios": hom, "tasa_homicidios": round(tasa_hom, 2),
            "robos": rob, "tasa_robos": round(tasa_rob, 1),
            "tasa_actividad_policial": round(tasa_pol, 1),
            "poblacion_estacional": 1 if municipio in POBLACION_ESTACIONAL else 0,
            "fuente": snic.CITA,
        })

    # El nivel se calcula al final, cuando estan todos: es relativo al conjunto.
    cortes = cortes_por_terciles([f["tasa_indice"] for f in filas])
    for f in filas:
        f["nivel"] = clasificar(f["tasa_indice"], cortes)
    return sorted(filas, key=lambda f: -f["tasa_indice"])


def guardar(filas: List[dict], path: Path = SQLITE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        # CREATE TABLE IF NOT EXISTS no agrega columnas a una tabla que ya
        # existe: una base de una corrida anterior se queda sin las nuevas.
        existentes = {c[1] for c in con.execute("PRAGMA table_info(seguridad)")}
        for columna, tipo in (("poblacion_estacional", "INTEGER NOT NULL DEFAULT 0"),):
            if columna not in existentes:
                con.execute(f"ALTER TABLE seguridad ADD COLUMN {columna} {tipo}")
        con.executemany(
            f"INSERT OR REPLACE INTO seguridad ({', '.join(COLUMNAS)}) "
            f"VALUES ({', '.join(':' + c for c in COLUMNAS)})",
            filas,
        )
        con.commit()
    finally:
        con.close()
    (SALIDA_DIR / "seguridad_86.json").write_text(
        json.dumps({"fuente": snic.CITA, "municipios": filas}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


ADVERTENCIAS = (
    "Son HECHOS DENUNCIADOS, no delitos ocurridos: donde se denuncia menos, el",
    "numero baja sin que baje el delito.",
    "El nivel es RELATIVO a los 86 municipios relevados, no absoluto: 'alto'",
    "significa 'en el tercio superior', no 'peligroso'.",
    "El indice deja afuera estupefacientes y armas, que se detectan por accion",
    "policial y no por denuncia de una victima. Se informan aparte porque miden",
    "despliegue de la fuerza, que es otra pregunta.",
    "Los partidos BALNEARIOS (*) tienen la tasa inflada: los hechos ocurren sobre",
    "la poblacion de verano y el denominador es la poblacion residente. No se",
    "corrige porque no hay dato de poblacion turistica por partido; se marca.",
)


def _num(x, decimales: int = 1) -> str:
    """Numero al castellano: punto para miles, coma para decimales.

    Hacia falta un helper porque el atajo .replace(",", ".") sobre un formato
    ingles convierte el separador de miles pero deja el decimal en punto, y
    2.324,8 salia impreso como "2.324.8", que no se puede leer.
    """
    s = f"{x:,.{decimales}f}"
    entero, _, dec = s.partition(".")
    entero = entero.replace(",", ".")
    return f"{entero},{dec}" if dec else entero


def ficha(municipio: str, path: Path = SQLITE) -> str:
    if not Path(path).exists():
        return "Sin analizar. Core: python src/seguridad/motor_seguridad.py --todos"
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        f = con.execute("SELECT * FROM seguridad WHERE municipio = ?", (municipio,)).fetchone()
        total = con.execute("SELECT COUNT(*) FROM seguridad").fetchone()[0]
        puesto = con.execute(
            "SELECT COUNT(*) FROM seguridad WHERE tasa_indice > "
            "(SELECT tasa_indice FROM seguridad WHERE municipio = ?)",
            (municipio,),
        ).fetchone()[0] + 1
    finally:
        con.close()
    if f is None:
        return f"{municipio}: sin datos del SNIC."

    return "\n".join([
        "=" * 74,
        f"{municipio.upper()}  -  seguridad {f['anio']}",
        "=" * 74,
        "",
        f"Nivel: {f['nivel'].upper()}   (puesto {puesto} de {total} por tasa)",
        *([
            "  ! Partido BALNEARIO: la tasa esta inflada porque los hechos ocurren",
            "    sobre la poblacion de verano y se dividen por la residente.",
        ] if f["poblacion_estacional"] else []),
        f"Tasa del indice: {_num(f['tasa_indice'])} hechos denunciados por 100.000 hab.",
        f"Hechos del indice: {_num(f['hechos_indice'], 0)}",
        "",
        f"   contra las personas    {_num(f['tasa_personas']):>10}",
        f"   contra la propiedad    {_num(f['tasa_propiedad']):>10}",
        f"   integridad sexual      {_num(f['tasa_sexual']):>10}",
        "",
        f"   homicidios dolosos     {f['homicidios']:>10}   (tasa {f['tasa_homicidios']})",
        f"   robos                  {f['robos']:>10}   (tasa {_num(f['tasa_robos'])})",
        "",
        f"Fuera del indice — actividad policial (drogas y armas): tasa {_num(f['tasa_actividad_policial'])}",
        "",
        "-" * 74,
        *ADVERTENCIAS,
        f"Fuente: {f['fuente']}",
    ])


def ranking(path: Path = SQLITE, limite: int = 25) -> str:
    if not Path(path).exists():
        return "Sin analizar. Core: python src/seguridad/motor_seguridad.py --todos"
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        filas = con.execute(
            "SELECT municipio, anio, nivel, tasa_indice, tasa_homicidios, tasa_robos, "
            "poblacion_estacional FROM seguridad ORDER BY tasa_indice DESC LIMIT ?", (limite,)
        ).fetchall()
        conteo = dict(con.execute("SELECT nivel, COUNT(*) FROM seguridad GROUP BY nivel").fetchall())
    finally:
        con.close()

    lineas = [
        "MUNICIPIOS POR TASA DE HECHOS DENUNCIADOS",
        "=" * 72,
        f"{'municipio':<26}{'nivel':<8}{'tasa':>10}{'homic.':>9}{'robos':>10}",
        "-" * 72,
    ]
    for m, a, n, t, th, tr, est in filas:
        # El asterisco no es decorativo: sin el, el lector concluye que la costa
        # es peligrosa cuando lo que pasa es que el denominador es chico.
        rotulo = f"{m} *" if est else m
        lineas.append(f"{rotulo:<26}{n:<8}{_num(t, 0):>10}{_num(th):>9}{_num(tr, 0):>10}")
    lineas += [
        "-" * 72,
        f"bajo: {conteo.get('bajo', 0)}   medio: {conteo.get('medio', 0)}   alto: {conteo.get('alto', 0)}",
        "",
        *ADVERTENCIAS,
    ]
    return "\n".join(lineas)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIP - Seguridad (SNIC)")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--todos", action="store_true", help="Calcular y guardar los 86")
    grupo.add_argument("--ficha", metavar="MUNICIPIO")
    grupo.add_argument("--ranking", action="store_true")
    parser.add_argument("--refrescar", action="store_true", help="Volver a bajar el CSV del SNIC")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.ficha:
        print(ficha(args.ficha))
        return 0
    if args.ranking:
        print(ranking())
        return 0

    filas = calcular(args.refrescar)
    if not filas:
        print("El SNIC no devolvio datos para ningun municipio del relevamiento.")
        return 1
    guardar(filas)
    print(f"{len(filas)} municipios, año {filas[0]['anio']} -> {SQLITE}")
    print()
    print(ranking())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
