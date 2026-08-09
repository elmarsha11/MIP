"""
Proveedor DeepSeek: cliente LLM agnóstico, con cache y cuota como Gemini.

DeepSeek es muy barato ($5 ≈ ilimitado para MIP) y escalable. Esta es la base
para reemplazar Gemini cuando la cuota gratuita se agote.

Arquitectura:
  1. **Cuota**: límites conservadores por minuto y por día (igual que Gemini).
  2. **Cache**: mismo schema que Gemini (hash del prompt + esquema).
  3. **Respaldo**: hasta 3 modelos en orden de preferencia.
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

import requests

from .provider import LLMProvider, CuotaAgotada


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "extraction" / "cache"
RUTA_CONTADOR = CACHE_DIR / "consumo_deepseek_diario.json"

# Modelos en orden de preferencia
# deepseek-chat es el más capaz; deepseek-reasoner es más lento y caro (no usar aqui).
MODELOS = ("deepseek-chat",)

# Limites conservadores (igual que Gemini)
RPM_MAX = 10  # DeepSeek es mas tolerante que Gemini en plan pago
RPD_MAX = 5000  # Con $5 cabe mucho mas, pero mantenemos conservador
TIMEOUT_SEGUNDOS = 30

ENDPOINT = "https://api.deepseek.com/chat/completions"


def leer_api_key() -> str:
    """Lee la clave de DeepSeek desde env var o archivo."""
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if key:
        return key
    ruta = PROJECT_ROOT / "deepseek_key.txt"
    if ruta.exists():
        key = ruta.read_text(encoding="utf-8").strip()
        if key:
            return key
    raise RuntimeError(
        "No hay clave de DeepSeek. Define DEEPSEEK_API_KEY o coloca la clave en deepseek_key.txt"
    )


class LimitadorCuota:
    """Igual que en gemini_client.py: RPM y RPD con persistencia."""

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
                    f"Tope diario alcanzado ({self.rpd_max} llamadas DeepSeek). "
                    "Vuelve mañana."
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


class ClienteDeepSeek(LLMProvider):
    """Cliente HTTP directo a DeepSeek API con cache y cuota."""

    def __init__(
        self,
        modelos: Sequence[str] = MODELOS,
        limitador: Optional[LimitadorCuota] = None,
        usar_cache: bool = True,
        cache_dir: Path = CACHE_DIR,
    ):
        self.modelos = list(modelos)
        self._limitador = limitador or LimitadorCuota()
        self.usar_cache = usar_cache
        self.cache_dir = Path(cache_dir)
        self._api_key = leer_api_key()
        self._modelo_vivo: Optional[str] = None
        self._llamadas_reales = 0
        self._aciertos_cache = 0

        if self.usar_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _clave(prompt: str, esquema: dict) -> str:
        semilla = prompt + "|" + json.dumps(esquema, sort_keys=True)
        return hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:20]

    def _path_cache(self, clave: str) -> Path:
        return self.cache_dir / f"ds_{clave}.json"

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

    @property
    def llamadas_reales(self) -> int:
        return self._llamadas_reales

    @property
    def aciertos_cache(self) -> int:
        return self._aciertos_cache

    @property
    def limitador(self) -> LimitadorCuota:
        return self._limitador

    def generar_json(self, prompt: str, esquema: dict) -> Optional[Dict[str, Any]]:
        """Genera JSON via DeepSeek con cache y fallback de modelos."""
        clave = self._clave(prompt, esquema)

        if self.usar_cache:
            cacheado = self._leer_cache(clave)
            if cacheado is not None:
                self._aciertos_cache += 1
                return cacheado

        for modelo in self.modelos:
            try:
                self._limitador.esperar_turno()
            except CuotaAgotada:
                raise

            try:
                respuesta = self._llamar_api(modelo, prompt, esquema)
                datos = json.loads(respuesta)
                datos["_modelo"] = modelo
                self._modelo_vivo = modelo
                self._llamadas_reales += 1
                if self.usar_cache:
                    self._escribir_cache(clave, datos)
                return datos
            except json.JSONDecodeError as e:
                print(f"    [DeepSeek {modelo}] JSON invalido: {str(e)[:90]}")
                continue
            except requests.RequestException as e:
                print(f"    [DeepSeek {modelo}] error de red: {str(e)[:90]}")
                continue
            except Exception as e:
                print(f"    [DeepSeek {modelo}] error: {str(e)[:90]}")
                continue

        print(f"    [DeepSeek] todos los modelos fallaron")
        return None

    def _llamar_api(self, modelo: str, prompt: str, esquema: dict) -> str:
        """Llama la API de DeepSeek con timeout y manejo de errores.

        Dos diferencias con Gemini que hay que compensar aca, no en extractor.py:

        1. DeepSeek NO acepta un `response_schema`: su modo JSON es solo
           {"type": "json_object"}, que garantiza JSON sintacticamente valido pero
           no su forma. Gemini si fuerza el esquema. Para que los dos devuelvan la
           misma estructura, el esquema se inyecta como texto en un mensaje de
           sistema.
        2. DeepSeek exige la palabra "json" en los mensajes cuando se pide ese
           modo; si falta, la API rechaza el pedido. El prompt de Fase 4 no la
           tiene (habla de citas y variables), asi que la aporta el sistema.
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        sistema = (
            "Respondé unicamente con un objeto json que valide contra este "
            "JSON Schema, sin texto alrededor ni bloques de codigo:\n"
            + json.dumps(esquema, ensure_ascii=False)
        )
        messages = [
            {"role": "system", "content": sistema},
            {"role": "user", "content": prompt},
        ]

        payload = {
            "model": modelo,
            "messages": messages,
            "response_format": {"type": "json_object"},
            # Fase 4 audita, no redacta: se quiere la lectura mas literal posible
            # del texto. La temperatura alta solo agregaria parafraseo, y una cita
            # parafraseada la tumba la verificacion de ADR-0014.
            "temperature": 0.0,
            "max_tokens": 8192,
        }

        resp = requests.post(
            ENDPOINT,
            headers=headers,
            json=payload,
            timeout=TIMEOUT_SEGUNDOS,
        )
        resp.raise_for_status()

        data = resp.json()
        # DeepSeek devuelve {"choices": [{"message": {"content": "..."}}]}
        if "choices" not in data or not data["choices"]:
            raise RuntimeError("Respuesta sin choices")
        return data["choices"][0]["message"]["content"]
