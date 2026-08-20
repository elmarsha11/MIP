"""
Informe de seguridad: los 86 juntos, para imprimir o repartir.

Es lo que la ficha por municipio no da: una vista de conjunto. La ficha sirve
para la visita a UN intendente; esto sirve para decidir a cuales visitar, o para
dejarlo en una reunion donde se habla de los 86 a la vez.

Dos tablas porque son dos preguntas con dos fuentes distintas (mismo criterio
que las dos hojas del Excel, ver libro_excel.exportar_seguridad):

  1. Cuanto — el indice del SNIC, denuncias por 100.000 habitantes.
  2. Como opera — que confirmo la prensa local en 12 meses, aspecto por aspecto.

Mezclarlas en una sola tabla haria parecer que un numero oficial y una nota de
diario pesan lo mismo.

Uso:
    python src/exportar/informe_seguridad_pdf.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
for _ruta in (PROJECT_ROOT / "src" / "tablero",):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

import consultas  # noqa: E402

from pdf_base import GRIS, LINEA, NEGRO, ROJO, _num, crear_pdf  # noqa: E402

SALIDA_DIR = PROJECT_ROOT / "data" / "processed" / "exportes"

# Las mismas 4 advertencias que consultas._seguridad adjunta a cada ficha, mas
# la de como-opera: el informe se lee suelto, sin la ficha al lado que las
# explique, asi que tienen que venir escritas ADENTRO del documento.
ADVERTENCIAS = [
    "Son hechos DENUNCIADOS, no delitos ocurridos: donde se denuncia menos, el "
    "número baja sin que baje el delito.",
    "El nivel es RELATIVO a los 86 municipios relevados. «Alto» significa «en "
    "el tercio superior», no «peligroso».",
    "El índice deja afuera estupefacientes y armas: se detectan por acción "
    "policial, no por denuncia de una víctima.",
    "Partidos BALNEARIO: la tasa está inflada porque los hechos ocurren sobre "
    "la población de verano y se dividen por la residente. Marcados abajo.",
    "«Cómo opera» sale de prensa local, últimos 12 meses. Ausencia de "
    "evidencia no es evidencia de ausencia: que la prensa leída no lo haya "
    "publicado no prueba que el municipio no lo tenga.",
]

ANCHO_UTIL = 277  # A4 apaisado menos margenes por defecto de fpdf2 (10mm c/u)


def _portada(pdf, familia: str, total: int) -> None:
    pdf.set_font(familia, "B", 20)
    pdf.set_text_color(*NEGRO)
    pdf.multi_cell(0, 9, "Informe de seguridad — los 86 municipios",
                    new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(familia, "", 9)
    pdf.set_text_color(*GRIS)
    pdf.multi_cell(
        0, 5,
        f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} · {total} municipios",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_font(familia, "B", 9)
    pdf.set_text_color(*ROJO)
    pdf.multi_cell(0, 5, "Confidencial — UDS. No distribuir fuera del equipo.",
                    new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_draw_color(*LINEA)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(3)

    pdf.set_font(familia, "B", 11)
    pdf.set_text_color(*NEGRO)
    pdf.multi_cell(0, 6, "Qué NO dice este informe", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    for texto in ADVERTENCIAS:
        pdf.set_font(familia, "", 8.5)
        pdf.set_text_color(*NEGRO)
        pdf.set_x(pdf.l_margin + 4)
        pdf.multi_cell(ANCHO_UTIL - 4, 4.3, f"•  {texto}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def _tabla_indice(pdf, familia: str, municipios: List[dict]) -> None:
    pdf.add_page()
    pdf.set_font(familia, "B", 13)
    pdf.set_text_color(*NEGRO)
    pdf.multi_cell(0, 7, "Cuánto — índice SNIC (hechos denunciados por 100.000 hab.)",
                    new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    filas = [["Municipio", "Nivel", "Tasa índice", "Homicidios",
              "Tasa homic.", "Robos", "Tasa robos", "Balneario"]]
    for m in sorted(municipios, key=lambda x: -(x["tasa_indice"] or 0)):
        filas.append([
            m["municipio"], m["nivel"] or "—", _num(m["tasa_indice"], 1),
            _num(m["homicidios"]), _num(m["tasa_homicidios"], 2),
            _num(m["robos"]), _num(m["tasa_robos"], 1),
            "sí" if m["poblacion_estacional"] else "",
        ])

    with pdf.table(
        filas, col_widths=(70, 24, 28, 28, 28, 24, 28, 27),
        text_align=("LEFT", "CENTER", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "CENTER"),
        line_height=5.2, first_row_as_headings=True,
    ) as tabla:
        pass
    del tabla


def _tabla_como_opera(pdf, familia: str, municipios: List[dict],
                      aspectos: List[dict]) -> None:
    pdf.add_page()
    pdf.set_font(familia, "B", 13)
    pdf.set_text_color(*NEGRO)
    pdf.multi_cell(0, 7, "Cómo opera — confirmado por prensa local (últimos 12 meses)",
                    new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # Etiquetas cortas SIN salto de linea forzado: fpdf2 ya envuelve el texto
    # solo, y forzar un \n en una palabra sin espacio la parte a la mitad
    # ("Patrul / la"). Se deja que decida donde cortar.
    etiquetas_cortas = {
        "patrulla_urbana": "Patrulla", "centro_monitoreo": "Cámaras",
        "alarmas_vecinales": "Alarmas", "policia_bonaerense": "Bonaerense",
        "fuerzas_federales": "Federales", "operativos": "Operativos",
        "allanamientos": "Allanam.",
    }
    claves = [a["clave"] for a in aspectos]
    encabezado = ["Municipio"] + [etiquetas_cortas.get(c, c) for c in claves]

    filas = [encabezado]
    for m in sorted(municipios, key=lambda x: x["municipio"]):
        por_clave = {a["clave"]: a["confirmado"] for a in m["aspectos"]}
        # "sí"/"" y no un tilde grafico (check-mark): depende de que la fuente
        # del sistema lo tenga, y en un informe que se imprime esto no se nota
        # hasta que alguien lo abre sin Arial.
        filas.append([m["municipio"]] + ["sí" if por_clave.get(c) else "—" for c in claves])

    with pdf.table(
        filas, col_widths=(35,) + (9,) * len(claves),
        text_align=("LEFT",) + ("CENTER",) * len(claves),
        line_height=5, first_row_as_headings=True,
    ) as tabla:
        pass
    del tabla

    pdf.ln(2)
    pdf.set_font(familia, "", 8)
    pdf.set_text_color(*GRIS)
    pdf.multi_cell(
        0, 4,
        f"Confirmados sobre {len(municipios)}: " + " · ".join(
            f"{a['etiqueta']} {a['n']}" for a in aspectos
        ),
        new_x="LMARGIN", new_y="NEXT",
    )


def exportar(salida: Optional[Path] = None) -> Optional[Path]:
    datos = consultas.seguridad()
    if not datos.get("hay_datos"):
        return None

    pdf, familia = crear_pdf("L")
    _portada(pdf, familia, datos["total"])
    _tabla_indice(pdf, familia, datos["municipios"])
    _tabla_como_opera(pdf, familia, datos["municipios"], datos["aspectos"])

    if salida is None:
        SALIDA_DIR.mkdir(parents=True, exist_ok=True)
        salida = SALIDA_DIR / f"MIP_seguridad_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    salida.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(salida))
    return salida


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="MIP - Informe de seguridad, los 86 juntos")
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ruta = exportar(args.salida)
    print(f"PDF -> {ruta}" if ruta else "Sin datos de seguridad. Corre el motor primero.")
    return 0 if ruta else 1


if __name__ == "__main__":
    sys.exit(main())
