"""
Tablero de MIP - servidor local.

    python src/tablero/servidor.py
    -> http://127.0.0.1:8765

Sin dependencias: solo biblioteca estandar. Corre en cualquier PC con Python,
sin pip install y sin cadena de paquetes de terceros. Para una herramienta
confidencial que tiene que ser portable, eso vale mas que la comodidad de un
framework.

Escucha SOLO en 127.0.0.1. No es accesible desde la red aunque la maquina este
en una wifi compartida. Publicarlo para el equipo es una decision aparte, que
necesita hosting privado y login, y no se toma por default.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

import acciones  # noqa: E402
import consultas  # noqa: E402

WEB = _AQUI / "web"
HOST = "127.0.0.1"
PUERTO = 8765


class Tablero(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    # -- utilidades --------------------------------------------------------

    def _json(self, datos: Any, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _csv(self, filas: list, nombre: str) -> None:
        buffer = io.StringIO()
        if filas:
            escritor = csv.DictWriter(buffer, fieldnames=list(filas[0].keys()))
            escritor.writeheader()
            escritor.writerows(filas)
        # utf-8-sig para que Excel en Windows no rompa los acentos.
        cuerpo = buffer.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato, *args):
        pass  # sin ruido en la consola

    # -- rutas -------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        ruta = urlparse(self.path)
        partes = [p for p in unquote(ruta.path).split("/") if p]
        query = parse_qs(ruta.query)

        if not partes or partes[0] != "api":
            return super().do_GET()

        try:
            if partes[1:] == ["resumen"]:
                return self._json(consultas.resumen())
            if partes[1:] == ["municipios"]:
                return self._json(consultas.municipios())
            if partes[1:2] == ["municipio"] and len(partes) == 3:
                ficha = consultas.ficha(partes[2])
                return self._json(ficha or {"error": "Municipio inexistente"}, 200 if ficha else 404)
            if partes[1:2] == ["resumen-municipio"] and len(partes) == 3:
                r = consultas.ficha_resumida(partes[2])
                return self._json(r or {"error": "Municipio inexistente"}, 200 if r else 404)
            if partes[1:] == ["turnos"]:
                return self._json(consultas.mapa_turnos())
            if partes[1:] == ["costo-turnos"]:
                return self._json(consultas.costo_turnos())
            if partes[1:] == ["territorio"]:
                return self._json(consultas.resumen_territorio())
            if partes[1:2] == ["territorio"] and len(partes) == 3:
                return self._json(consultas.territorio(partes[2]))
            if partes[1:] == ["ambiental"]:
                return self._json(consultas.ambiental())
            if partes[1:] == ["comercial"]:
                return self._json(consultas.comercial())
            if partes[1:] == ["revision"]:
                return self._json(consultas.cola_de_revision())
            if partes[1:] == ["parametros"]:
                return self._json(consultas.parametros_impacto())
            if partes[1:] == ["acciones"]:
                return self._json(acciones.listar_acciones())
            if partes[1:] == ["tareas"]:
                return self._json(acciones.tareas())
            if partes[1:2] == ["tarea"] and len(partes) == 3:
                return self._json(acciones.estado(partes[2]))
            if partes[1:2] == ["exportar"] and len(partes) == 3:
                return self._exportar(partes[2])
            if partes[1:2] == ["descargar"] and len(partes) == 3:
                return self._descargar(partes[2])
            if partes[1:2] == ["descargar"] and len(partes) == 4:
                return self._descargar(partes[2], partes[3])
        except Exception as exc:  # que un error no tumbe el tablero
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

        return self._json({"error": "Ruta desconocida"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        ruta = urlparse(self.path)
        if unquote(ruta.path) != "/api/accion":
            return self._json({"error": "Ruta desconocida"}, 404)
        largo = int(self.headers.get("Content-Length") or 0)
        try:
            cuerpo = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "JSON invalido"}, 400)
        resultado = acciones.lanzar(cuerpo.get("accion", ""), cuerpo.get("municipio"))
        return self._json(resultado, 400 if "error" in resultado else 200)

    def _descargar(self, que: str, nombre: Optional[str] = None) -> None:
        """Sirve un archivo generado, si existe.

        La ruta se resuelve y se comprueba que caiga ADENTRO de la carpeta de
        exportes. Sin eso, un nombre de municipio con ".." serviria cualquier
        archivo de la maquina: el servidor escucha solo en 127.0.0.1, pero un
        agujero de path traversal no se deja abierto porque hoy nadie lo alcance.
        """
        from consultas import PROJECT_ROOT

        base = (PROJECT_ROOT / "data" / "processed" / "exportes").resolve()
        if que == "excel":
            candidatos = sorted(base.glob("MIP_*.xlsx"), reverse=True)
            destino = candidatos[0] if candidatos else None
        elif que == "ficha" and nombre:
            seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in nombre)
            destino = base / "fichas" / f"MIP_{seguro.replace(' ', '_')}.pdf"
        elif que == "html":
            tablero = (PROJECT_ROOT / "data" / "processed" / "tablero").resolve()
            candidatos = sorted(tablero.glob("MIP_tablero_*.html"), reverse=True)
            destino = candidatos[0] if candidatos else None
            base = tablero
        else:
            return self._json({"error": "Descarga desconocida"}, 404)

        if destino is None:
            return self._json({"error": "Todavia no se genero. Corre la accion primero."}, 404)
        destino = destino.resolve()
        if base not in destino.parents or not destino.exists():
            return self._json({"error": "No disponible"}, 404)

        datos = destino.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{destino.name}"')
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _archivo(self, ruta, nombre: str, tipo: str) -> None:
        cuerpo = Path(ruta).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _exportar(self, que: str) -> None:
        if que == "municipios.csv":
            return self._csv(consultas.municipios(), "mip_municipios.csv")
        if que == "turnos.csv":
            mapa = consultas.mapa_turnos()
            filas = [{**f, "grupo": "con canal digital"} for f in mapa["digitales"]]
            filas += [{**f, "grupo": "sin canal digital (ausencia probada)"} for f in mapa["sin_digital"]]
            return self._csv(filas, "mip_turnos.csv")
        if que == "territorio.csv":
            filas = []
            for m in consultas.resumen_territorio()["municipios"]:
                filas += consultas.territorio(m["municipio"])["entidades"]
            return self._csv(filas, "mip_territorio.csv")
        if que == "revision.csv":
            return self._csv(consultas.cola_de_revision(), "mip_revision.csv")
        if que == "costo-turnos.csv":
            datos = consultas.costo_turnos()
            filas = [
                {**f, "advertencia": "ESTIMACION con supuestos sin fuente - no es ahorro fiscal"}
                for f in datos.get("municipios", [])
            ]
            return self._csv(filas, "mip_costo_turnos.csv")
        if que == "ambiental.xlsx":
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "exportar"))
            from libro_excel import exportar_ambiental

            return self._archivo(exportar_ambiental(), "mip_ambiental.xlsx",
                                 "application/vnd.openxmlformats-officedocument."
                                 "spreadsheetml.sheet")
        return self._json({"error": "Exportacion desconocida"}, 404)


def main() -> int:
    if not WEB.exists():
        print(f"Falta la carpeta {WEB}")
        return 1
    servidor = ThreadingHTTPServer((HOST, PUERTO), Tablero)
    url = f"http://{HOST}:{PUERTO}"
    print(f"\n  Tablero de MIP  ->  {url}")
    print("  Solo escucha en esta maquina. Ctrl+C para cortar.\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  Tablero cerrado.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
