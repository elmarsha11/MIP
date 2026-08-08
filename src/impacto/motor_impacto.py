"""
Fase 5 - Motor de impacto (CLI).

Cruza los hallazgos de Fase 4 con el Gold Standard y calcula el costo social de
no tener turnos de salud digitales, solo donde la ausencia esta probada.

Uso:
    python src/impacto/motor_impacto.py --turnos
    python src/impacto/motor_impacto.py --turnos --csv salida.csv
    python src/impacto/motor_impacto.py --parametros
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
for _r in (_AQUI, PROJECT_ROOT / "src" / "discovery"):
    if str(_r) not in sys.path:
        sys.path.insert(0, str(_r))

from discovery_engine import cargar_municipios  # noqa: E402

from modelo_turnos import (  # noqa: E402
    CostoSocial,
    advertencias,
    calcular,
    sensibilidad,
    techo_de_precio_anual,
)
from parametros import CATALOGO, TipoParametro, parametros_sin_fuente  # noqa: E402

SQLITE_HALLAZGOS = PROJECT_ROOT / "data" / "processed" / "extraction" / "hallazgos_86.sqlite"

# Canales que prueban que HOY no hay via digital. no_verificable no entra:
# no saber no es lo mismo que saber que no.
CANALES_SIN_DIGITAL = ("telefono", "presencial")


def _plata(x: float) -> str:
    return f"${x:,.0f}".replace(",", ".")


def municipios_sin_canal_digital(sqlite_path: Path = SQLITE_HALLAZGOS) -> List[CostoSocial]:
    if not Path(sqlite_path).exists():
        raise FileNotFoundError(
            f"No existe {sqlite_path}. Corre Fase 4 primero: "
            "python src/extraction/extraction_engine.py --all"
        )
    poblaciones = {m.nombre: (m.id_municipio, m.poblacion) for m in cargar_municipios()}

    con = sqlite3.connect(sqlite_path)
    try:
        filas = con.execute(
            "SELECT municipio, valor, fragmento, url FROM hallazgos "
            "WHERE variable = 'canal_turnos_salud' AND estado = 'verificado' "
            "AND valor IN (%s) ORDER BY municipio" % ",".join("?" * len(CANALES_SIN_DIGITAL)),
            CANALES_SIN_DIGITAL,
        ).fetchall()
    finally:
        con.close()

    resultados = []
    for municipio, canal, fragmento, url in filas:
        id_mun, poblacion = poblaciones.get(municipio, (None, None))
        if not id_mun or not poblacion:
            # ADR-0009: sin poblacion no se calcula. No se estima.
            print(f"  [omitido] {municipio}: sin poblacion en el Gold Standard")
            continue
        resultados.append(
            calcular(municipio, id_mun, poblacion, canal, fragmento or "", url)
        )
    return sorted(resultados, key=lambda c: c.costo_central, reverse=True)


def informe_turnos(costos: List[CostoSocial]) -> str:
    lineas = [
        "",
        "=" * 78,
        "COSTO SOCIAL DE NO TENER TURNOS DE SALUD DIGITALES",
        "=" * 78,
        "",
    ]
    for a in advertencias():
        lineas.append(f"  ! {a}")
    lineas.append("")
    lineas.append(
        f"{'Municipio':<24}{'Hab.':>9}{'Canal':>12}{'Costo social anual (rango)':>32}"
    )
    lineas.append("-" * 78)
    for c in costos:
        rango = f"{_plata(c.costo_min)} a {_plata(c.costo_max)}"
        lineas.append(f"{c.municipio:<24}{c.poblacion:>9,}{c.canal_actual:>12}{rango:>32}".replace(",", "."))
    lineas.append("-" * 78)

    total_min = sum(c.costo_min for c in costos)
    total_max = sum(c.costo_max for c in costos)
    habitantes = sum(c.poblacion for c in costos)
    lineas += [
        f"{len(costos)} municipios con ausencia probada, {habitantes:,} habitantes".replace(",", "."),
        f"Costo social anual agregado: {_plata(total_min)} a {_plata(total_max)}",
        "",
        "TECHO DE PRECIO (10% del valor devuelto, decision comercial de UDS):",
    ]
    for c in costos[:5]:
        t_min, _, t_max = techo_de_precio_anual(c)
        lineas.append(
            f"  {c.municipio:<24} hasta {_plata(t_min)} a {_plata(t_max)} por ano "
            f"({_plata(t_min / 12)} a {_plata(t_max / 12)} por mes)"
        )
    ancho = total_max / total_min if total_min else 0
    lineas += [
        "",
        f"QUE MEDIR PRIMERO (hoy el resultado varia {ancho:.0f} veces entre el piso y el techo,",
        " y un rango asi no sirve para vender: el numero grande y el chico cuentan",
        " historias distintas. Esto es lo que hay que cerrar, en orden):",
    ]
    for nombre, factor, como in sensibilidad():
        lineas.append(f"  {factor:.1f}x  {nombre}")
        lineas.append(f"        -> {como}")
    lineas += [
        "",
        "EVIDENCIA (por que se afirma que hoy no hay canal digital):",
    ]
    for c in costos[:6]:
        lineas.append(f'  {c.municipio}: "{(c.evidencia or "")[:88]}"')
    lineas.append("=" * 78)
    return "\n".join(lineas)


def informe_parametros() -> str:
    lineas = ["", "PARAMETROS DEL MODELO", "=" * 78]
    for p in CATALOGO.values():
        marca = "OK " if p.es_afirmable else "!! "
        lineas.append(f"{marca}{p.nombre}  =  {p.valor} {p.unidad}   [{p.tipo.value}]")
        lineas.append(f"     fuente: {p.citar()}")
        if p.nota:
            lineas.append(f"     nota: {p.nota[:150]}")
        lineas.append("")
    faltan = parametros_sin_fuente()
    lineas.append(
        f"{len(faltan)} parametro(s) sin fuente. ADR-0009: un dato faltante genera una "
        "tarea de investigacion, no un numero inventado."
    )
    lineas.append("Mientras sigan asi, el modelo devuelve rangos y se rotula como estimacion.")
    return "\n".join(lineas)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIP Fase 5 - Modelo de impacto")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--turnos", action="store_true", help="Costo social de turnos no digitales")
    grupo.add_argument("--parametros", action="store_true", help="Muestra los parametros y sus fuentes")
    parser.add_argument("--csv", type=Path, help="Exporta el detalle a CSV")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.parametros:
        print(informe_parametros())
        return 0

    costos = municipios_sin_canal_digital()
    if not costos:
        print("No hay municipios con ausencia probada de canal digital. Nada que calcular.")
        return 0
    print(informe_turnos(costos))

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([
                "id_municipio", "municipio", "poblacion", "canal_actual",
                "costo_social_min", "costo_social_central", "costo_social_max",
                "costo_por_habitante", "evidencia", "url", "advertencia",
            ])
            for c in costos:
                w.writerow([
                    c.id_municipio, c.municipio, c.poblacion, c.canal_actual,
                    round(c.costo_min), round(c.costo_central), round(c.costo_max),
                    round(c.por_habitante()), c.evidencia, c.url or "",
                    "ESTIMACION con supuestos sin fuente - no es ahorro fiscal",
                ])
        print(f"\nCSV -> {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
