"""
Proveedor Gemini: re-exporta ClienteGemini que ya implementa LLMProvider.

ClienteGemini ya tiene todo lo que necesitamos (cuota, cache, rotación de modelos).
Este módulo simplemente lo re-exporta bajo el nombre GeminiProvider para que
factory.py pueda tratar Gemini y DeepSeek de forma uniforme.
"""
