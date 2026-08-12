"""
Motor de gabinete: quien gobierna cada municipio, con el decreto que lo prueba.

    Fase 3 encontro DONDE mirar. Fase 4 reporto QUE DICEN los portales.
    Esto responde QUIEN ESTA A CARGO, que es a quien hay que ir a ver.

Por que no alcanza con un buscador ni con los diarios locales: el 2026-08-09 se
comparo el gabinete de Chascomus que devuelven ambos contra el Boletin Oficial.
Siete de ocho secretarios coincidian. El octavo no, y la diferencia tenia fecha:

    ene 2026   Marino 19 menciones, Funes  4
    abr 2026   Marino  9 menciones, Funes  2   <- Marino todavia firma Obras
    may 2026   Marino  0 menciones, Funes  7   <- firma Funes
    jun 2026   Marino  0 menciones, Funes 11

Jorge Marino fue Secretario de Obras hasta abril de 2026 y Lucas Funes firma
desde mayo. Las dos citas son literales y las dos son correctas: lo que las
ordena es la FECHA DEL DECRETO. Por eso `fecha_norma` no es un adorno — sin ella
la base no distingue quien ESTA de quien ESTUVO, que es todo lo que se le pide.

Uso:
    python src/gabinete/motor_gabinete.py --municipio Chascomus
    python src/gabinete/motor_gabinete.py --all
    python src/gabinete/motor_gabinete.py --ficha Chascomus
    python src/gabinete/motor_gabinete.py --cobertura
"""

from __future__ import annotations

import argparse
import re
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
from portal import paginas_del_portal  # noqa: E402

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
    fecha_norma TEXT,
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
            "url", "fuente", "confianza", "fecha", "fecha_norma", "modelo")


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

    boletines = sibom.boletines(municipio, maximo=maximo_boletines)
    autoridades, rechazadas = leer(
        municipio, id_municipio, boletines, cliente, fecha, TipoFuente.BOLETIN_OFICIAL
    )

    # Segunda fuente. Corre SIEMPRE, no solo cuando el boletin no dio nada: su
    # otro trabajo es contrastar. Un cargo que las dos fuentes nombran igual vale
    # mucho mas que uno que solo vio una, y un cargo donde se contradicen es
    # precisamente el que hay que mirar a ojo.
    paginas = paginas_del_portal(municipio, id_municipio)
    del_portal, rechazadas_portal = leer(
        municipio, id_municipio, paginas, cliente, fecha, TipoFuente.PORTAL
    )
    autoridades += del_portal
    rechazadas += rechazadas_portal

    if verbose:
        print(
            f"  boletines: {len(boletines)} ({sum(len(f.texto) for f in boletines)} chars)"
            f" | portal: {len(paginas)} paginas ({sum(len(p.texto) for p in paginas)} chars)"
        )

    return MunicipioGabinete(
        municipio=municipio,
        id_municipio=id_municipio,
        fecha=fecha,
        boletines_leidos=len(boletines),
        caracteres_analizados=(
            sum(len(f.texto) for f in boletines) + sum(len(p.texto) for p in paginas)
        ),
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
        # La tabla puede venir de una corrida anterior sin fecha_norma:
        # CREATE TABLE IF NOT EXISTS no agrega columnas a una tabla que ya existe.
        existentes = {c[1] for c in con.execute("PRAGMA table_info(autoridades)")}
        if "fecha_norma" not in existentes:
            con.execute("ALTER TABLE autoridades ADD COLUMN fecha_norma TEXT")
        for r in resultados:
            # NO se borra el municipio antes de escribir.
            #
            # La primera version si lo hacia, con el argumento de que el gabinete
            # es una foto y un secretario que se fue tiene que desaparecer. El
            # argumento es bueno y el efecto fue malo: la extraccion NO es
            # determinista —una corrida devolvio 9 secretarias de Chascomus y la
            # siguiente 6, con la misma evidencia disponible— asi que reescribir
            # perdio dos secretarias reales que nadie habia dejado.
            #
            # Ahora cada cargo se actualiza por su cuenta y solo lo pisa un
            # decreto MAS NUEVO. Un secretario que se fue no desaparece, pero su
            # fecha se queda vieja y la ficha lo marca "sin firmar hace meses".
            # Es ADR-0013: la base no se destruye a si misma. Preferimos un dato
            # viejo y fechado a un vacio silencioso.
            for fila in r.autoridades:
                d = fila.to_row()
                previa = con.execute(
                    "SELECT fecha_norma FROM autoridades WHERE id = ?", (d["id"],)
                ).fetchone()
                if previa and previa[0] and d["fecha_norma"] and previa[0] > d["fecha_norma"]:
                    continue  # lo guardado es de un decreto mas nuevo
                con.execute(
                    f"INSERT OR REPLACE INTO autoridades ({', '.join(COLUMNAS)}) "
                    f"VALUES ({', '.join('?' for _ in COLUMNAS)})",
                    tuple(d[c] for c in COLUMNAS),
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


def _distinto(a: str, b: str) -> bool:
    """Dos nombres son la misma persona salvo tildes, mayusculas y espacios.

    Sin esto, "Marcela E. Arias" y "Marcela Arias" se reportarian como
    contradiccion entre fuentes, y el aviso perderia todo su valor por ruido.
    """
    import unicodedata

    def norma(x):
        t = unicodedata.normalize("NFKD", str(x or "").lower())
        t = "".join(c for c in t if not unicodedata.combining(c))
        return {p for p in re.split(r"[^a-z0-9]+", t) if len(p) > 1}

    na, nb = norma(a), norma(b)
    if not na or not nb:
        return True
    # Comparten el apellido y algo mas: es la misma persona con el nombre
    # escrito con mas o menos detalle.
    return not (na <= nb or nb <= na)


def _tres_meses_antes(iso: str) -> str:
    """'2026-06' a partir de '2026-09-15'. Sin dateutil: solo aritmetica de mes."""
    anio, mes = int(iso[:4]), int(iso[5:7])
    mes -= 3
    if mes <= 0:
        anio, mes = anio - 1, mes + 12
    return f"{anio:04d}-{mes:02d}"


def ficha(municipio: str, path: Path = SQLITE_GABINETE) -> str:
    if not Path(path).exists():
        return f"Sin analizar. Core: python src/gabinete/motor_gabinete.py --municipio {municipio}"
    con = sqlite3.connect(path)
    try:
        filas = con.execute(
            "SELECT cargo, area, nombre, cita, url, confianza, fecha_norma, fuente "
            "FROM autoridades WHERE municipio = ? ORDER BY cargo, area",
            (municipio,),
        ).fetchall()
    finally:
        con.close()
    if not filas:
        return f"{municipio}: sin autoridades detectadas (o todavia sin analizar)."

    # Un cargo puede venir de dos fuentes. Gana el boletin, que es un decreto
    # publicado; el portal queda como corroboracion o como discrepancia. Nunca se
    # descarta la segunda en silencio: que dos fuentes se contradigan es un dato,
    # y es el que dispara la revision humana.
    _PESO_FUENTE = {"boletin_oficial": 0, "portal": 1, "red_oficial": 2}
    por_cargo: dict = {}
    for f in filas:
        por_cargo.setdefault((f[0], (f[1] or "").lower()), []).append(f)
    for grupo in por_cargo.values():
        grupo.sort(key=lambda f: _PESO_FUENTE.get(f[7], 9))
    filas = [g[0] for g in por_cargo.values()]
    filas.sort(key=lambda f: (f[0], f[1] or ""))
    otras = {
        (g[0][0], (g[0][1] or "").lower()): [x for x in g[1:] if _distinto(x[2], g[0][2])]
        for g in por_cargo.values()
    }

    # La evidencia mas fresca del municipio marca el pulso. Un cargo cuya ultima
    # prueba es de varios meses antes no esta necesariamente vacante, pero no se
    # puede afirmar igual que uno que firmo el mes pasado. Chascomus tenia una
    # Secretaria de Recursos Humanos probada en diciembre de 2025 y nunca mas.
    fechas = [f[6] for f in filas if f[6]]
    mas_fresca = max(fechas) if fechas else None

    lineas = ["=" * 74, f"{municipio.upper()}  -  cupula municipal", "=" * 74]
    for cargo, area, nombre, cita, url, confianza, fecha_norma, fuente in filas:
        titulo = "INTENDENTE" if cargo == "intendente" else f"Secretaria de {area or '?'}"
        # La fecha del decreto va al lado del nombre y no al pie: un gabinete
        # cambia, y "quien es" sin "desde cuando" es la mitad del dato.
        sello = f"decreto del {fecha_norma}" if fecha_norma else "sin fecha de norma"
        rezagado = (
            mas_fresca and fecha_norma and fecha_norma[:7] < _tres_meses_antes(mas_fresca)
        )
        lineas += [
            "",
            f"{titulo}: {nombre}   [{confianza}, {sello}]"
            + ("   <-- sin firmar hace meses, confirmar" if rezagado else ""),
            f'  Prueba: "{cita[:190]}"',
            f"  {url}",
        ]
        for otro in otras.get((cargo, (area or "").lower()), []):
            lineas += [
                f"  !! el {otro[7]} dice {otro[2]} -- revisar cual esta vigente",
                f'     "{otro[3][:150]}"',
                f"     {otro[4]}",
            ]
    lineas += ["", "-" * 74,
               "Cada nombre sale de una cita literal verificada contra el boletin.",
               "La fecha es la del decreto, no la del analisis: es lo que distingue",
               "quien ESTA de quien ESTUVO."]
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
