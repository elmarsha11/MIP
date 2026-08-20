"""
Una ficha PDF por municipio, para llevarle impresa a un intendente.

Es lo contrario del Excel. El Excel sirve para comparar los 86 y decidir a quien
visitar; esto sirve para la visita: un documento de pocas paginas sobre UN
municipio, que se imprime y se deja sobre la mesa.

Por eso el orden no es el de la base sino el de una conversacion: primero quien
es el municipio, despues que le pasa, al final que se le puede vender. Y cada
afirmacion con su cita, porque la ficha se lee delante de la persona que mejor
sabe si es cierta.

Uso:
    python src/exportar/ficha_pdf.py --municipio Chascomus
    python src/exportar/ficha_pdf.py --todos
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
for _ruta in (PROJECT_ROOT / "src" / "tablero", PROJECT_ROOT / "src" / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

import consultas  # noqa: E402

from pdf_base import GRIS, LINEA, NEGRO, ROJO, _num, crear_pdf  # noqa: E402

SALIDA_DIR = PROJECT_ROOT / "data" / "processed" / "exportes" / "fichas"


class Ficha:
    """Envuelve a FPDF con las pocas primitivas que esta ficha necesita."""

    def __init__(self, municipio: str):
        self.pdf, self.familia = crear_pdf("P")
        self.municipio = municipio

    def _f(self, tam: int, negrita: bool = False, color=NEGRO):
        self.pdf.set_font(self.familia, "B" if negrita else "", tam)
        self.pdf.set_text_color(*color)

    def titulo(self, texto: str, subtitulo: str = "") -> None:
        self._f(20, True)
        self.pdf.multi_cell(0, 9, texto, new_x="LMARGIN", new_y="NEXT")
        if subtitulo:
            self._f(9, False, GRIS)
            self.pdf.multi_cell(0, 5, subtitulo, new_x="LMARGIN", new_y="NEXT")
        self.pdf.ln(3)

    def seccion(self, texto: str) -> None:
        if self.pdf.get_y() > 250:
            self.pdf.add_page()
        self.pdf.ln(3)
        self._f(12, True)
        self.pdf.multi_cell(0, 6, texto, new_x="LMARGIN", new_y="NEXT")
        self.pdf.set_draw_color(*LINEA)
        y = self.pdf.get_y()
        self.pdf.line(self.pdf.l_margin, y, self.pdf.w - self.pdf.r_margin, y)
        self.pdf.ln(2)

    ANCHO_ROTULO = 58

    def dato(self, rotulo: str, valor: str, destacado: bool = False) -> None:
        """Rotulo a la izquierda, valor a la derecha.

        El rotulo se recorta si no entra: `cell` no trunca, y un area larga como
        "Obras, Servicios Publicos y Ambiente" se pegaba al nombre del secretario
        dejando "...y AmbienteLucas Funes".
        """
        self._f(9, False, GRIS)
        while self.pdf.get_string_width(rotulo) > self.ANCHO_ROTULO - 3 and len(rotulo) > 8:
            rotulo = rotulo[:-2] + "…"
        self.pdf.cell(self.ANCHO_ROTULO, 5, rotulo)
        self._f(11 if destacado else 9, destacado)
        self.pdf.multi_cell(0, 5, valor or "—", new_x="LMARGIN", new_y="NEXT")

    def parrafo(self, texto: str, tam: int = 9, color=NEGRO) -> None:
        self._f(tam, False, color)
        self.pdf.multi_cell(0, 4.5, texto, new_x="LMARGIN", new_y="NEXT")

    def cita(self, texto: str, origen: str = "") -> None:
        """La cita va sangrada y en gris: es lo que sostiene la afirmacion de
        arriba y tiene que poder leerse sin taparla."""
        if self.pdf.get_y() > 258:
            self.pdf.add_page()
        self._f(8, False, GRIS)
        self.pdf.set_x(self.pdf.l_margin + 6)
        self.pdf.multi_cell(0, 4, f'"{texto}"', new_x="LMARGIN", new_y="NEXT")
        if origen:
            self._f(7, False, GRIS)
            self.pdf.set_x(self.pdf.l_margin + 6)
            self.pdf.multi_cell(0, 3.5, origen, new_x="LMARGIN", new_y="NEXT")
        self.pdf.ln(1)

    def guardar(self, ruta: Path) -> Path:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.pdf.output(str(ruta))
        return ruta


def _armar(nombre: str) -> Optional[Ficha]:
    f = consultas.ficha_resumida(nombre)
    if not f:
        return None

    p, g, c = f["poblacion"], f["seguridad"], f["como_opera"]
    aut, sal, edu = f["autoridades"], f["salud"], f["educacion"]

    d = Ficha(nombre)
    d.titulo(
        nombre,
        f"MIP — Municipal Intelligence Platform · {f['id_municipio']} · "
        f"generado el {datetime.now().strftime('%d/%m/%Y')}",
    )

    d.seccion("El municipio")
    d.dato("Habitantes", _num(p.get("total")), destacado=True)
    if p.get("mujeres"):
        # Coma decimal: el resto de la ficha ya la usa y mezclar separadores
        # en el mismo documento se lee como un error de armado.
        pct = lambda x: str(x).replace(".", ",")
        d.dato("Mujeres", f"{_num(p['mujeres'])}   ({pct(p['pct_mujeres'])}%)")
        d.dato("Varones", f"{_num(p['varones'])}   ({pct(p['pct_varones'])}%)")
    d.parrafo(p.get("fuente") or "", 7, GRIS)
    if f.get("sitio_oficial"):
        d.dato("Sitio oficial", f["sitio_oficial"])

    d.seccion("Autoridades")
    intendente = aut.get("intendente")
    d.dato("Intendente", (intendente or {}).get("nombre") or "sin dato verificado",
           destacado=bool(intendente))
    if intendente:
        d.cita(intendente["cita"], f"{intendente['fuente']} · decreto del "
                                   f"{intendente.get('fecha_norma') or 's/f'}")
    for s in aut.get("secretarios") or []:
        d.dato(s.get("area") or "Secretaría", s["nombre"])
    if not aut.get("secretarios"):
        d.parrafo("Sin secretarías verificadas en el Boletín Oficial.", 8, GRIS)

    d.seccion("Seguridad — cuánto delito se denuncia")
    if g.get("disponible"):
        d.dato("Nivel", f"{g['nivel'].upper()}   (puesto {g['puesto']} de {g['total']})",
               destacado=True)
        d.dato("Tasa", f"{_num(g['tasa_indice'], 1)} por 100.000 hab. · {g['anio']}")
        d.dato("Homicidios dolosos", _num(g["homicidios"]))
        d.dato("Robos", _num(g["robos"]))
        d.pdf.ln(1)
        for a in g.get("advertencias", []):
            d.parrafo(f"· {a}", 7, GRIS)
    else:
        d.parrafo("El SNIC no publica datos de este municipio.", 8, GRIS)

    d.seccion("Seguridad — qué tiene y cómo opera")
    if c.get("disponible") and c.get("notas"):
        d.parrafo(f"{c['medios_leidos']} medios leídos · {c['notas']} notas en 12 meses",
                  7, GRIS)
        d.pdf.ln(1)
        for a in c.get("aspectos", []):
            ev = a.get("evidencia")
            d.dato(a["etiqueta"], "sí" if ev else "sin evidencia", destacado=bool(ev))
            if ev:
                d.cita(ev["cita"], f"{ev['medio']} · {ev['fecha_nota']}")
        d.parrafo(c.get("advertencia") or "", 7, GRIS)
    else:
        d.parrafo("Sus medios locales no exponen archivo consultable.", 8, GRIS)

    d.seccion("Territorio y servicios")
    d.dato("Hospitales", _num(len(sal.get("hospitales") or [])))
    d.dato("CAPS / salas", _num(sal.get("caps")))
    d.dato("Farmacias", _num(sal.get("farmacias")))
    d.dato("Establecimientos educativos", _num(edu.get("total")))
    d.parrafo(edu.get("fuente") or "", 7, GRIS)

    d.seccion("Qué le puede vender UDS")
    ops = consultas.comercial()
    mios = next((m for m in ops.get("municipios", []) if m["municipio"] == nombre), None)
    if mios:
        d.parrafo(f"{len(mios['oportunidades'])} oportunidades detectadas · "
                  f"potencial {mios['puntaje']}", 8, GRIS)
        d.pdf.ln(1)
        for o in mios["oportunidades"]:
            d.dato(o["friccion"].upper(), o["producto"], destacado=True)
            d.parrafo(o["problema"], 8)
            d.cita(o["cita"], o["url"])
    else:
        d.parrafo("Sin oportunidades detectadas con la evidencia disponible.", 8, GRIS)

    d.seccion("")
    d.parrafo(
        "Cada afirmación de esta ficha lleva su cita textual y su fuente. Los "
        "vacíos son vacíos declarados: MIP no estima ni completa lo que no pudo "
        "verificar.", 7, GRIS)
    d.parrafo("Documento confidencial — UDS. No distribuir fuera del equipo.", 7, ROJO)
    return d


def exportar(nombre: str, salida: Optional[Path] = None) -> Optional[Path]:
    d = _armar(nombre)
    if d is None:
        return None
    if salida is None:
        seguro = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in nombre)
        salida = SALIDA_DIR / f"MIP_{seguro.replace(' ', '_')}.pdf"
    return d.guardar(salida)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MIP - Ficha PDF por municipio")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--municipio")
    grupo.add_argument("--todos", action="store_true")
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.municipio:
        ruta = exportar(args.municipio, args.salida)
        print(f"PDF -> {ruta}" if ruta else f"{args.municipio}: no está en los 86.")
        return 0 if ruta else 1

    hechas = 0
    for m in consultas.municipios():
        ruta = exportar(m["municipio"])
        if ruta:
            hechas += 1
    print(f"{hechas} fichas -> {SALIDA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
