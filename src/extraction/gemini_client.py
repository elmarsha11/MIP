"""
Cliente de Gemini para Fase 4: cuota, cache y respaldo de modelos.

Tres cosas que MIP necesita para funcionar solo (ADR-0014):

  1. **No excederse.** Limitador de pedidos por minuto y por dia. Si se llega al
     tope diario, se corta con un error claro en vez de seguir pegandole a la API.
  2. **No pagar dos veces.** Todo se cachea por hash del prompt. Re-correr un
     municipio cuyo portal no cambio no gasta una sola llamada.
  3. **No morir cuando retiran un modelo.** Se prueban varios en orden. Paso de
     verdad: el 2026-08-07 gemini-2.5-flash dejo de estar disponible para cuentas
     nuevas y el ETL anterior hubiera dejado de andar sin aviso.

El limitador esta tomado de cerebro_gemini.py, que ya lo tenia bien resuelto.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUTA_CREDENCIAL = PROJECT_ROOT / "credenciales.txt"
CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "extraction" / "cache"
RUTA_CONTADOR = CACHE_DIR / "consumo_diario.json"

# Orden de preferencia. El primero disponible gana.
# 'latest' antes que una version fija: las versiones fijas se retiran sin aviso.
#
# La cuota del plan gratuito es POR MODELO, no por cuenta: verificado el
# 2026-08-07, con gemini-2.0-flash agotado mientras los otros dos respondian.
# Por eso la lista es larga: cuando uno se queda sin cuota, la corrida sigue.
MODELOS = (
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
)

# Limites propios, conservadores a proposito: la consigna es no excederse, no
# bloquearse y no generar cargos. Los limites REALES del proveedor son mas
# ajustados y no estan publicados por modelo, asi que ademas se reacciona al 429.
RPM_MAX = 4
RPD_MAX = 200
TIMEOUT_SEGUNDOS = 45  # colgarse 90s en un modelo lento sale mas caro que rotar

# Cuanto se espera antes de volver a probar un modelo que devolvio 429.
# Los limites del plan gratuito son mayormente por minuto: un minuto de espera
# suele alcanzar para que el modelo vuelva.
ENFRIAMIENTO_429 = 65
# Cuantos 429 seguidos hacen falta para dar un modelo por agotado hasta manana.
MAX_429_POR_MODELO = 3
# Cuanto se banca esperar cuando TODOS los modelos estan enfriandose.
MAX_ESPERA_TOTAL = 140


class CuotaAgotada(RuntimeError):
    """Se llego al tope diario. No es un error de red: es una decision."""


class SinCredencial(RuntimeError):
    pass


def leer_api_key() -> str:
    """Variable de entorno primero, archivo despues.

    GEMINI_API_KEY permite correr MIP sin dejar la clave escrita en un archivo
    dentro de una carpeta que sincroniza con la nube.
    """
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if key:
        return key
    if RUTA_CREDENCIAL.exists():
        key = RUTA_CREDENCIAL.read_text(encoding="utf-8").strip()
        if key:
            return key
    raise SinCredencial(
        "No hay clave de Gemini. Defini la variable de entorno GEMINI_API_KEY "
        f"o pone la clave en {RUTA_CREDENCIAL.name} (esta en .gitignore)."
    )


class LimitadorCuota:
    """Pedidos por minuto y por dia, compartido entre hilos.

    El contador diario se persiste en disco: si el proceso se corta y se vuelve
    a lanzar, no se resetea la cuenta del dia y no se pasa del limite.
    """

    def __init__(self, rpm_max: int = RPM_MAX, rpd_max: int = RPD_MAX):
        self.rpm_max = rpm_max
        self.rpd_max = rpd_max
        self._marcas: deque = deque()
        self._lock = threading.Lock()
        self._dia, self._usadas = self._leer_contador()

    def _leer_contador(self):
        hoy = time.strftime("%Y-%m-%d")
        try:
            datos = json.loads(RUTA_CONTADOR.read_text(encoding="utf-8"))
            if datos.get("dia") == hoy:
                return hoy, int(datos.get("usadas", 0))
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return hoy, 0

    def _guardar_contador(self) -> None:
        try:
            RUTA_CONTADOR.parent.mkdir(parents=True, exist_ok=True)
            RUTA_CONTADOR.write_text(
                json.dumps({"dia": self._dia, "usadas": self._usadas}), encoding="utf-8"
            )
        except OSError:
            pass

    def restantes_hoy(self) -> int:
        return max(0, self.rpd_max - self._usadas)

    def esperar_turno(self) -> None:
        with self._lock:
            hoy = time.strftime("%Y-%m-%d")
            if hoy != self._dia:
                self._dia, self._usadas = hoy, 0

            if self._usadas >= self.rpd_max:
                raise CuotaAgotada(
                    f"Tope diario alcanzado ({self.rpd_max} llamadas). "
                    "Los municipios ya procesados quedaron guardados; "
                    "volve a correr manana y sigue desde donde quedo."
                )

            ahora = time.time()
            while self._marcas and ahora - self._marcas[0] > 60:
                self._marcas.popleft()
            if len(self._marcas) >= self.rpm_max:
                espera = 60 - (ahora - self._marcas[0]) + 0.5
                if espera > 0:
                    time.sleep(espera)
                ahora = time.time()
                while self._marcas and ahora - self._marcas[0] > 60:
                    self._marcas.popleft()

            self._marcas.append(time.time())
            self._usadas += 1
            self._guardar_contador()


def _es_falla_permanente(mensaje: str) -> bool:
    """Distingue "este modelo no existe" de "esta vez no contesto".

    Importa: dar por muerto un modelo que solo tuvo un timeout achica la cadena
    de respaldo justo cuando mas se la necesita.
    """
    m = mensaje.lower()
    return any(s in m for s in ("404", "not_found", "no longer available", "not supported"))


class ClienteGemini:
    """Genera contenido estructurado, con cache en disco y respaldo de modelos."""

    def __init__(
        self,
        modelos: Sequence[str] = MODELOS,
        limitador: Optional[LimitadorCuota] = None,
        usar_cache: bool = True,
        cache_dir: Path = CACHE_DIR,
    ):
        self.modelos = list(modelos)
        self.limitador = limitador or LimitadorCuota()
        self.usar_cache = usar_cache
        self.cache_dir = Path(cache_dir)
        self._cliente = None
        self._modelo_vivo: Optional[str] = None
        self._lock = threading.Lock()
        # modelo -> momento en que vuelve a estar disponible tras un 429
        self._enfriamiento: Dict[str, float] = {}
        self._429_seguidos: Dict[str, int] = {}
        self._agotados: set = set()
        self.llamadas_reales = 0
        self.aciertos_cache = 0
        if self.usar_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- infraestructura ---------------------------------------------------

    def _obtener_cliente(self):
        with self._lock:
            if self._cliente is None:
                from google import genai  # import diferido: solo si se usa IA
                from google.genai import types

                # El timeout es obligatorio, no decorativo. Sin el, una conexion
                # colgada deja el proceso esperando para siempre: paso el
                # 2026-08-07, una corrida quedo 5 horas dormida sin avanzar ni
                # fallar. Un motor que tiene que andar solo no puede colgarse en
                # silencio.
                self._cliente = genai.Client(
                    api_key=leer_api_key(),
                    http_options=types.HttpOptions(timeout=TIMEOUT_SEGUNDOS * 1000),
                )
            return self._cliente

    def _path_cache(self, clave: str) -> Path:
        return self.cache_dir / f"ia_{clave}.json"

    @staticmethod
    def _clave(prompt: str, esquema: dict) -> str:
        semilla = prompt + "|" + json.dumps(esquema, sort_keys=True)
        return hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:20]

    # -- API ---------------------------------------------------------------

    def generar_json(self, prompt: str, esquema: dict) -> Optional[Dict[str, Any]]:
        """Devuelve el JSON estructurado, o None si no se pudo.

        None no es una excepcion silenciada: el llamador lo traduce a
        'no_verificable', que es una respuesta valida (ADR-0009).
        """
        clave = self._clave(prompt, esquema)

        if self.usar_cache:
            cacheado = self._leer_cache(clave)
            if cacheado is not None:
                self.aciertos_cache += 1
                return cacheado

        config = {"response_mime_type": "application/json", "response_schema": esquema}
        ultimo_error: Optional[Exception] = None

        # Dos vueltas: en la segunda ya vencieron los enfriamientos de la primera.
        for _ in range(2):
            for modelo in self._orden_de_intento():
                try:
                    self.limitador.esperar_turno()
                except CuotaAgotada:
                    raise
                try:
                    respuesta = self._obtener_cliente().models.generate_content(
                        model=modelo, contents=prompt, config=config
                    )
                    datos = json.loads(respuesta.text)
                    datos["_modelo"] = modelo
                    self._modelo_vivo = modelo
                    self._429_seguidos[modelo] = 0
                    self.llamadas_reales += 1
                    if self.usar_cache:
                        self._escribir_cache(clave, datos)
                    return datos
                except Exception as exc:  # 429, modelo retirado, JSON roto...
                    ultimo_error = exc
                    mensaje = str(exc)
                    if "RESOURCE_EXHAUSTED" in mensaje or "429" in mensaje:
                        self._marcar_429(modelo)
                    elif _es_falla_permanente(mensaje):
                        # Modelo retirado o inexistente para esta cuenta: no
                        # tiene sentido volver a probarlo en toda la corrida.
                        print(f"    [modelo {modelo} no existe] {mensaje[:90]}")
                        self._agotados.add(modelo)
                    else:
                        # Timeout o corte de red: puede ser pasajero. Se enfria
                        # y se rota, pero sigue siendo candidato.
                        print(f"    [modelo {modelo} no respondio] {mensaje[:90]}")
                        self._enfriamiento[modelo] = time.time() + ENFRIAMIENTO_429

            # Ningun modelo disponible. Si alguno esta por volver, se espera.
            if not self._esperar_a_que_vuelva_alguno():
                break

        if all(m in self._agotados for m in self.modelos):
            raise CuotaAgotada(
                "Todos los modelos agotaron su cuota. Los municipios ya procesados "
                "quedaron guardados: volve a correr con --reanudar mas tarde o "
                "manana y sigue desde donde quedo."
            )
        print(f"    [IA sin respuesta] ultimo error: {str(ultimo_error)[:130]}")
        return None

    # -- rotacion de modelos -----------------------------------------------

    def _orden_de_intento(self) -> List[str]:
        """Modelos disponibles ahora, con el que ya funciono primero."""
        ahora = time.time()
        disponibles = [
            m
            for m in self.modelos
            if m not in self._agotados and self._enfriamiento.get(m, 0) <= ahora
        ]
        if self._modelo_vivo in disponibles:
            disponibles.remove(self._modelo_vivo)
            disponibles.insert(0, self._modelo_vivo)
        return disponibles

    def _marcar_429(self, modelo: str) -> None:
        seguidos = self._429_seguidos.get(modelo, 0) + 1
        self._429_seguidos[modelo] = seguidos
        if seguidos >= MAX_429_POR_MODELO:
            self._agotados.add(modelo)
            print(f"    [cuota] {modelo} agotado por hoy, se descarta")
        else:
            self._enfriamiento[modelo] = time.time() + ENFRIAMIENTO_429
            print(f"    [cuota] {modelo} sin cupo, se prueba otro modelo")

    def _esperar_a_que_vuelva_alguno(self) -> bool:
        """Espera a que venza el enfriamiento mas cercano. False si no vale la pena."""
        ahora = time.time()
        pendientes = [
            t for m, t in self._enfriamiento.items() if m not in self._agotados and t > ahora
        ]
        if not pendientes:
            return False
        espera = min(pendientes) - ahora
        if espera > MAX_ESPERA_TOTAL:
            return False
        print(f"    [cuota] esperando {espera:.0f}s a que se libere un modelo...")
        time.sleep(max(1, espera))
        return True

    # -- cache -------------------------------------------------------------

    def _leer_cache(self, clave: str) -> Optional[Dict[str, Any]]:
        path = self._path_cache(clave)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _escribir_cache(self, clave: str, datos: Dict[str, Any]) -> None:
        try:
            self._path_cache(clave).write_text(
                json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass


class ClienteFalso:
    """Cliente que devuelve respuestas fijas. Para tests, sin red ni cuota."""

    def __init__(self, respuestas: Optional[List[Optional[dict]]] = None):
        self.respuestas = list(respuestas or [])
        self.prompts: List[str] = []
        self.llamadas_reales = 0
        self.aciertos_cache = 0

    def generar_json(self, prompt: str, esquema: dict) -> Optional[Dict[str, Any]]:
        self.prompts.append(prompt)
        self.llamadas_reales += 1
        return self.respuestas.pop(0) if self.respuestas else None


__all__ = [
    "MODELOS",
    "RPD_MAX",
    "RPM_MAX",
    "ClienteFalso",
    "ClienteGemini",
    "CuotaAgotada",
    "LimitadorCuota",
    "SinCredencial",
    "leer_api_key",
]
