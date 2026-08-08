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
            if partes[1:] == ["turnos"]:
                return self._json(consultas.mapa_turnos())
            if partes[1:] == ["costo-turnos"]:
                return self._json(consultas.costo_turnos())
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

    def _exportar(self, que: str) -> None:
        if que == "municipios.csv":
            return self._csv(consultas.municipios(), "mip_municipios.csv")
        if que == "turnos.csv":
            mapa = consultas.mapa_turnos()
            filas = [{**f, "grupo": "con canal digital"} for f in mapa["digitales"]]
            filas += [{**f, "grupo": "sin canal digital (ausencia probada)"} for f in mapa["sin_digital"]]
            return self._csv(filas, "mip_turnos.csv")
        if que == "revision.csv":
            return self._csv(consultas.cola_de_revision(), "mip_revision.csv")
        if que == "costo-turnos.csv":
            datos = consultas.costo_turnos()
            filas = [
                {**f, "advertencia": "ESTIMACION con supuestos sin fuente - no es ahorro fiscal"}
                for f in datos.get("municipios", [])
            ]
            return self._csv(filas, "mip_costo_turnos.csv")
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
