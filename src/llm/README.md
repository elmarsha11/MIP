# Capa LLM: Proveedores agnósticos

Esta capa abstrae el proveedor LLM (Gemini, DeepSeek, etc.) detrás de una interfaz única. Permite cambiar de proveedor sin tocar `src/extraction/`.

## Arquitectura

```
┌─────────────────┐
│ extraction.py   │  Usa LLMProvider (agnóstico)
└────────┬────────┘
         │
    ┌────▼────────────┐
    │ factory.py      │  Elige proveedor por env var
    └────┬───┬────────┘
         │   │
    ┌────▼─┐│    ┌──────────────┐
    │      │└───▶│ deepseek_    │  ClienteDeepSeek
    │Gemini│     │ provider.py  │  ($5 ≈ ilimitado)
    │      │     └──────────────┘
    └──────┘
```

## Uso

### Por defecto: Gemini
```bash
python src/extraction/extraction_engine.py --all
```

### Cambiar a DeepSeek por variable de entorno
```bash
# En bash/zsh
export MIP_LLM_PROVIDER=deepseek
python src/extraction/extraction_engine.py --all

# O en una línea
MIP_LLM_PROVIDER=deepseek python src/extraction/extraction_engine.py --all
```

### En código Python
```python
from src.llm import crear_proveedor

# Gemini (default)
llm = crear_proveedor()

# DeepSeek explícito
llm = crear_proveedor("deepseek")

# Desde env var
llm = crear_proveedor()  # Lee MIP_LLM_PROVIDER
```

## Configuración de claves API

### Gemini
- Env var: `GEMINI_API_KEY`
- Archivo: `credenciales.txt` (en `.gitignore`)

### DeepSeek
- Env var: `DEEPSEEK_API_KEY` (recomendado)
- Archivo: `deepseek_key.txt` (en `.gitignore`)

## Interfaces

Todos los proveedores implementan `LLMProvider`:

```python
def generar_json(self, prompt: str, esquema: dict) -> Optional[Dict]:
    """Genera JSON estructurado o None si no se pudo."""

@property
def llamadas_reales(self) -> int:
    """Llamadas reales a la API (sin cache)."""

@property
def aciertos_cache(self) -> int:
    """Veces que se devolvió del cache."""

@property
def limitador(self) -> LimitadorCuota:
    """Gestor de cuota por minuto y por día."""
```

## Agregar un nuevo proveedor

1. Crear `src/llm/nuevo_proveedor.py` que implemente `LLMProvider`
2. Agregar en `factory.py`:
   ```python
   elif proveedor == "nuevo":
       return ClienteNuevo(usar_cache=True)
   ```
3. Definirvariable de entorno si es necesario

## Cache

- **Gemini**: `data/processed/extraction/cache/ia_*.json`
- **DeepSeek**: `data/processed/extraction/cache/ds_*.json`

Cada proveedor tiene su propio prefijo para evitar colisiones.

## Cuota

- **Gemini**: 200 RPD (plan gratuito), 4 RPM
- **DeepSeek**: 5000 RPD (plan pago, $5), 10 RPM

Los límites son conservadores. Si se agotan, se guarda lo procesado y `--reanudar` retoma mañana.
