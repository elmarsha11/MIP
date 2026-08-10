"""
Interfaz abstracta para proveedores LLM.

MIP necesita un contrato único (generar_json + cache + cuota) independiente del
proveedor. Esto permite cambiar Gemini ↔ DeepSeek sin tocar extraction_engine.py.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLMProvider(ABC):
    """Contrato que todo proveedor LLM debe cumplir."""

    @abstractmethod
    def generar_json(self, prompt: str, esquema: dict) -> Optional[Dict[str, Any]]:
        """Genera JSON estructurado o None si no se pudo.

        Args:
            prompt: El texto a procesar
            esquema: JSON schema para validar la respuesta

        Returns:
            Dict con la respuesta estructurada + campo "_modelo" con nombre del modelo usado.
            None si la API no pudo responder (timeout, sin cuota, etc).

        Raises:
            CuotaAgotada: Si se alcanzó el límite diario/por minuto.
        """

    @property
    @abstractmethod
    def llamadas_reales(self) -> int:
        """Cuántas llamadas reales hizo a la API (sin cachés)."""

    @property
    @abstractmethod
    def aciertos_cache(self) -> int:
        """Cuántas veces devolvió del cache (sin llamar API)."""

    @property
    @abstractmethod
    def limitador(self) -> "LimitadorCuota":
        """Objeto que maneja límites de cuota por minuto y por día."""


class CuotaAgotada(RuntimeError):
    """Se llegó al tope diario. No es un error de red: es una decisión."""
