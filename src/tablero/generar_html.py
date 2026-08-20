"""
Genera el tablero como UN SOLO archivo HTML autonomo.

    python src/tablero/generar_html.py

Produce data/processed/tablero/MIP_tablero_AAAA-MM-DD.html: un archivo que se
abre con doble click, sin Python, sin servidor y sin internet. Todo adentro:
estilos, codigo y datos.

Para que sirve, y para que NO:

    SIRVE   pasarselo al equipo de UDS, abrirlo en una reunion sin conexion,
            dejarlo como foto fechada de como estaba la base ese dia.

    NO SIRVE para operar. Los botones que lanzan el motor no existen aca:
            atras no hay Python. Para trabajar se usa el servidor.

Reutiliza el MISMO frontend que el servidor. app.js detecta si los datos vienen
incrustados o por HTTP y se adapta. Mantener dos interfaces separadas seria
garantizar que en dos semanas muestren cosas distintas.

OJO: este archivo lleva adentro toda la base de conocimiento de MIP, que es el
activo comercial. Es facil de compartir por diseno, asi que hay que tratarlo con
el mismo cuidado que al SQLite.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

import consultas  # noqa: E402

PROJECT_ROOT = _AQUI.parents[1]
WEB = _AQUI / "web"
SALIDA_DIR = PROJECT_ROOT / "data" / "processed" / "tablero"


def reunir_datos() -> dict:
    """Todo lo que el tablero necesita, resuelto de una vez."""
    municipios = consultas.municipios()
    return {
        "generado": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
        "resumen": consultas.resumen(),
        "municipios": municipios,
        "turnos": consultas.mapa_turnos(),
        "costo_turnos": consultas.costo_turnos(),
        "revision": consultas.cola_de_revision(),
        "comercial": consultas.comercial(),
        "ambiental": consultas.ambiental(),
        "seguridad": consultas.seguridad(),
        "parametros": consultas.parametros_impacto(),
        "territorio": consultas.resumen_territorio(),
        # Las fichas se precalculan: sin servidor no hay a quien preguntarle.
        "fichas": {m["municipio"]: consultas.ficha(m["municipio"]) for m in municipios},
        "resumenes": {
            m["municipio"]: consultas.ficha_resumida(m["municipio"]) for m in municipios
        },
        # Los censos tambien se precalculan: sin servidor no hay a quien
        # preguntarle. Solo los municipios censados, para no inflar el archivo.
        "territorios": {
            m["municipio"]: consultas.territorio(m["municipio"])
            for m in consultas.resumen_territorio()["municipios"]
        },
    }


def generar(destino: Path | None = None) -> Path:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "estilo.css").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    datos = reunir_datos()

    # </script> dentro de los datos cerraria la etiqueta antes de tiempo.
    json_datos = json.dumps(datos, ensure_ascii=False, default=str).replace("</", "<\\/")

    html = html.replace(
        '<link rel="stylesheet" href="estilo.css">', f"<style>\n{css}\n</style>"
    )
    html = html.replace(
        '<script src="app.js"></script>',
        f"<script>window.DATOS_MIP = {json_datos};</script>\n<script>\n{js}\n</script>",
    )
    html = html.replace(
        '<div class="confidencial" title="Solo Juli y el equipo de UDS">CONFIDENCIAL — UDS</div>',
        '<div class="confidencial" title="Solo Juli y el equipo de UDS">'
        f'CONFIDENCIAL — UDS · foto del {datos["generado"]}</div>',
    )

    if destino is None:
        SALIDA_DIR.mkdir(parents=True, exist_ok=True)
        destino = SALIDA_DIR / f"MIP_tablero_{datetime.now().strftime('%Y-%m-%d')}.html"
    destino.write_text(html, encoding="utf-8")
    return destino


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    destino = generar(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    tam = destino.stat().st_size / 1024
    print(f"\n  Tablero generado: {destino}")
    print(f"  {tam:.0f} KB. Se abre con doble click. No necesita Python ni internet.")
    print("\n  Es una FOTO fechada, no la herramienta de trabajo: no trae los botones")
    print("  que lanzan el motor. Para operar, usar el servidor.")
    print("\n  Lleva adentro toda la base. Tratarlo con el cuidado del activo que es.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
