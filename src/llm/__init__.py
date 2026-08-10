"""Capa LLM: proveedores agnósticos (Gemini, DeepSeek, etc)."""

from .provider import LLMProvider, CuotaAgotada
from .factory import crear_proveedor

__all__ = [
    "LLMProvider",
    "CuotaAgotada",
    "crear_proveedor",
]
