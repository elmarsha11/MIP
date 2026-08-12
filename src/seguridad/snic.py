"""
Descarga y lectura del SNIC: estadistica criminal oficial por partido.

Fuente: Direccion Nacional de Estadistica Criminal, Ministerio de Seguridad de
la Nacion. Es a la seguridad lo que INDEC es a la poblacion: el dato duro,
fechado y comparable contra el que se calibra todo lo demas.

Lo que trae, medido el 2026-08-12:
  - 2000 a 2025, anual
  - 151 departamentos bonaerenses con datos en los ultimos anios
  - 69 tipos de delito, una fila por delito/departamento/anio
  - `tasa_hechos` ya calculada por cada 100.000 habitantes

Lo que NO trae, y hay que decirlo cada vez que se muestre el numero:
  **mide denuncias, no delitos.** Dos partidos con el mismo delito real pero
  distinta cultura de denuncia dan distinto. Es la mejor fuente que existe y es
  oficial, pero el rotulo honesto es "hechos denunciados", no "inseguridad".
"""

from __future__ import annotations

import csv
import io
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

import requests

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
if str(PROJECT_ROOT / "src" / "discovery") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src" / "discovery"))

SALIDA_DIR = PROJECT_ROOT / "data" / "processed" / "seguridad"
CACHE_DIR = SALIDA_DIR / "cache"
URL_CSV = "https://cloud-snic.minseg.gob.ar/Bases/SNIC/snic-departamentos-anual.csv"
ARCHIVO = "snic-departamentos-anual.csv"

CITA = (
    "Ministerio de Seguridad de la Nacion, Direccion Nacional de Estadistica "
    "Criminal. Sistema Nacional de Informacion Criminal (SNIC), serie por "
    "departamentos."
)

# Como nombra el SNIC a los partidos que el Gold Standard escribe distinto.
# Verificado uno por uno contra la lista de departamentos bonaerenses, nunca por
# parecido: asignarle a un municipio el delito de otro es el peor error posible
# en un modulo que va a calificar municipios. Es el tercer mapeo de este tipo en
# el proyecto —ya existen ALIAS_INDEC y ALIAS_OSM— y coincide casi entero.
#
# Son VARIOS nombres por municipio porque el SNIC se renombra a si mismo a mitad
# de la serie: Coronel Rosales figura como "Coronel de Marina L. Rosales" hasta
# 2016 y como "Coronel de Marina Leonardo Rosales" desde 2017. Con un solo alias
# el partido perdia nueve anios de datos, y como el modulo pedia el ultimo anio
# comun a todos, arrastraba a los 86 a 2016. Una fuente puede cambiarle el
# nombre a sus propias filas.
ALIAS_SNIC = {
    "General Madariaga": ("General Juan Madariaga",),
    "San Miguel del Monte": ("Monte",),
    "Veinticinco de Mayo": ("25 de Mayo",),
    "Alem": ("Leandro N. Alem",),
    "Coronel Rosales": (
        "Coronel de Marina Leonardo Rosales",   # 2017 en adelante
        "Coronel de Marina L. Rosales",         # hasta 2016
    ),
    "Gonzales Cháves": ("Adolfo Gonzales Chaves",),
}


class Hecho(NamedTuple):
    municipio: str
    anio: int
    delito: str
    hechos: int
    tasa: float


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t)


def _numero(v) -> Optional[float]:
    """El SNIC usa coma decimal: '1638,9565' es mil seiscientos treinta y ocho."""
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).strip().replace(".", "").replace(",", "."))
    except ValueError:
        return None


def bajar(refrescar: bool = False) -> str:
    """El CSV completo, del cache si esta.

    Son 67 MB y la serie de un anio cerrado no cambia, asi que se cachea. A
    diferencia de los cuadros de INDEC —360 KB, que si se versionan— este NO va
    al repositorio: pesa demasiado para el valor que agrega estar adentro.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    destino = CACHE_DIR / ARCHIVO
    if destino.exists() and not refrescar:
        return destino.read_text(encoding="utf-8", errors="replace")

    resp = requests.get(
        URL_CSV, timeout=600, headers={"User-Agent": "MIP-relevamiento-municipal/0.1"}
    )
    resp.raise_for_status()
    texto = resp.content.decode("utf-8-sig", errors="replace")
    # Solo se cachea el acierto: un CSV truncado congelaria datos incompletos.
    if len(texto) > 1_000_000:
        try:
            destino.write_text(texto, encoding="utf-8")
        except OSError:
            pass
    return texto


def leer(refrescar: bool = False) -> Dict[str, List[Hecho]]:
    """Hechos de los municipios del Gold Standard, indexados por nombre.

    Se filtra a Buenos Aires y se traduce el nombre del departamento al del
    Gold Standard. Un departamento que no corresponde a ninguno de los 86 se
    descarta: el relevamiento son 86, no los 135.
    """
    from discovery_engine import cargar_municipios

    # slug del nombre SNIC -> nombre del Gold Standard. Un municipio puede tener
    # mas de un nombre en la fuente a lo largo de la serie.
    equivalencias = {}
    for m in cargar_municipios():
        for nombre in ALIAS_SNIC.get(m.nombre, (m.nombre,)):
            equivalencias[_normalizar(nombre)] = m.nombre

    salida: Dict[str, List[Hecho]] = {}
    lector = csv.DictReader(io.StringIO(bajar(refrescar)), delimiter=";")
    for fila in lector:
        if "buenos aires" not in (fila.get("provincia_nombre") or "").lower():
            continue
        municipio = equivalencias.get(_normalizar(fila.get("departamento_nombre")))
        if municipio is None:
            continue
        try:
            anio = int(fila["anio"])
        except (KeyError, TypeError, ValueError):
            continue
        hechos = _numero(fila.get("cantidad_hechos"))
        tasa = _numero(fila.get("tasa_hechos"))
        salida.setdefault(municipio, []).append(
            Hecho(
                municipio=municipio,
                anio=anio,
                delito=(fila.get("codigo_delito_snic_nombre") or "").strip(),
                hechos=int(hechos) if hechos is not None else 0,
                tasa=tasa if tasa is not None else 0.0,
            )
        )
    return salida


COBERTURA_MINIMA = 0.9


def ultimo_anio(datos: Dict[str, List[Hecho]]) -> Optional[int]:
    """El anio mas reciente con cobertura suficiente para comparar.

    Todos los municipios tienen que estar en el MISMO anio: comparar 2025 de uno
    contra 2019 de otro seria un ranking falso.

    Pero exigir el anio comun a TODOS tampoco sirve. La primera version lo hacia
    y devolvia 2016 —diez anios viejo— porque un solo partido tenia un hueco.
    Sacrificar nueve anios de actualidad de 85 municipios por uno es peor que
    declarar que a ese uno le falta el dato.

    Se toma entonces el anio mas nuevo que cubra al menos el 90%, y el llamador
    informa quien queda afuera. Un municipio sin dato se muestra sin dato.
    """
    if not datos:
        return None
    por_anio: Dict[int, int] = {}
    for hechos in datos.values():
        for anio in {h.anio for h in hechos}:
            por_anio[anio] = por_anio.get(anio, 0) + 1

    minimo = len(datos) * COBERTURA_MINIMA
    suficientes = [a for a, n in por_anio.items() if n >= minimo]
    return max(suficientes) if suficientes else None


def sin_datos_en(datos: Dict[str, List[Hecho]], anio: int) -> List[str]:
    """Municipios que no tienen ninguna fila en ese anio. Se declaran."""
    return sorted(m for m, hechos in datos.items() if not any(h.anio == anio for h in hechos))


__all__ = ["ALIAS_SNIC", "CITA", "Hecho", "bajar", "leer", "sin_datos_en", "ultimo_anio"]
