"""
Factory para elegir proveedor LLM según configuración.

Uso:
    # Valor por defecto (Gemini)
    proveedor = crear_proveedor()

    # Cambiar a DeepSeek
    proveedor = crear_proveedor(proveedor="deepseek")

    # O por variable de entorno
    MIP_LLM_PROVIDER=deepseek python extraction_engine.py --all
"""

import os
import sys
from pathlib import Path
from typing import Optional

from .provider import LLMProvider
from .deepseek_provider import ClienteDeepSeek


def _importar_gemini_client():
    """Importa ClienteGemini de src/extraction usando importlib."""
    import importlib.util

    _AQUI = Path(__file__).resolve().parent
    _gemini_path = _AQUI.parent / "extraction" / "gemini_client.py"

    spec = importlib.util.spec_from_file_location("gemini_client", _gemini_path)
    gemini_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gemini_module)

    return gemini_module.ClienteGemini


def crear_proveedor(proveedor: Optional[str] = None) -> LLMProvider:
    """Crea una instancia del proveedor LLM.

    Args:
        proveedor: "gemini", "deepseek", o None (lee env var MIP_LLM_PROVIDER, default "gemini").

    Returns:
        Instancia de un LLMProvider listo para usar.

    Raises:
        ValueError si el nombre de proveedor no existe.
        SinCredencial si no hay clave API.
    """
    if proveedor is None:
        proveedor = os.environ.get("MIP_LLM_PROVIDER", "gemini").lower()

    proveedor = proveedor.lower().strip()

    if proveedor == "gemini":
        ClienteGemini = _importar_gemini_client()
        return ClienteGemini(usar_cache=True)
    elif proveedor == "deepseek":
        return ClienteDeepSeek(usar_cache=True)
    else:
        raise ValueError(
            f"Proveedor desconocido: {proveedor}. "
            "Opciones: 'gemini', 'deepseek'."
        )
