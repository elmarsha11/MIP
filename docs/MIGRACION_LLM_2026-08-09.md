# Migración: Capa LLM agnóstica (2026-08-09)

## Qué cambió

Se creó una **capa LLM abstracta** que desvincula Fase 4 del proveedor específico.

### Antes
- `extraction_engine.py` acoplado a `ClienteGemini`
- Para cambiar a otro modelo, había que reescribir lógica

### Ahora
- `extraction_engine.py` usa `LLMProvider` (interfaz agnóstica)
- Cambia de Gemini ↔ DeepSeek con **una variable de entorno**
- Fácil agregar más proveedores

## Estructura

```
src/llm/                          # Capa LLM agnóstica (nueva)
  ├── provider.py                 # Interfaz LLMProvider
  ├── factory.py                  # Factory para elegir proveedor
  ├── deepseek_provider.py        # Implementación DeepSeek (nueva)
  ├── gemini_provider.py          # Wrapper de gemini_client
  ├── __init__.py
  └── README.md

src/extraction/
  ├── extraction_engine.py        # Ya no importa ClienteGemini, usa factory
  ├── gemini_client.py            # Sin cambios (encapsulado en LLMProvider)
  ├── extractor.py
  ├── ...
```

## Cómo usar

### Opción 1: Gemini (default)
```bash
python src/extraction/extraction_engine.py --all
```

### Opción 2: DeepSeek por variable de entorno
```bash
# bash/zsh/sh
export MIP_LLM_PROVIDER=deepseek
python src/extraction/extraction_engine.py --all

# O en una línea
MIP_LLM_PROVIDER=deepseek python src/extraction/extraction_engine.py --all

# PowerShell
$env:MIP_LLM_PROVIDER = "deepseek"
python src/extraction/extraction_engine.py --all
```

### Opción 3: Desde Python
```python
from src.llm import crear_proveedor

# Gemini
llm = crear_proveedor("gemini")

# DeepSeek
llm = crear_proveedor("deepseek")

# Desde env var
llm = crear_proveedor()  # Lee MIP_LLM_PROVIDER
```

## Configuración de claves API

### Gemini
- **Env var** (recomendado): `GEMINI_API_KEY=...`
- **Archivo** (fallback): `credenciales.txt` (en `.gitignore`)

### DeepSeek
- **Env var** (recomendado): `DEEPSEEK_API_KEY=...`
- **Archivo** (fallback): `deepseek_key.txt` (en `.gitignore`)

## Beneficios

### Escalabilidad
- **Gemini**: Cuota gratuita limitada (200 RPD), se agota
- **DeepSeek**: $5 ≈ ilimitado para MIP, escalable

### Confiabilidad
- Ambos tienen **cache en disco** (no repite llamadas)
- **Limitador de cuota** por minuto y por día
- **Fallback de modelos** si uno se retira

### Mantenibilidad
- Un proveedor nuevo = implementar `LLMProvider` + una línea en factory
- El resto de MIP no cambia

## Próximos pasos

### Fase 2 (Validación con DeepSeek)
1. Correr un municipio pequeño con DeepSeek
2. Comparar hallazgos contra Gemini
3. Si coincide → escalar a los 86

### Fase 3 (Producción)
- DeepSeek como primario (`MIP_LLM_PROVIDER=deepseek` por defecto)
- Gemini como fallback (si DeepSeek falla)
- Cron/scheduler para re-ejecuciones autónomas

## Archivos nuevos

- `src/llm/provider.py` — Interfaz LLMProvider
- `src/llm/deepseek_provider.py` — Cliente DeepSeek
- `src/llm/factory.py` — Factory para elegir proveedor
- `src/llm/__init__.py` — Exports públicos
- `src/llm/README.md` — Documentación técnica
- `deepseek_key.txt` — Clave API de DeepSeek (gitignore)

## Archivos modificados

- `src/extraction/extraction_engine.py` — Ahora usa `crear_proveedor()` en lugar de `ClienteGemini`
- `.gitignore` — Agregado `deepseek_key.txt`

## Sin cambios (compatibilidad total)

- `src/extraction/gemini_client.py` — Encapsulado, sin breaking changes
- `src/extraction/extractor.py` — Sigue igual
- `src/extraction/fetcher.py` — Sigue igual
- Fase 3, 5, 6, Tablero — Nada que tocar
