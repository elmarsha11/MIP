"""
Catalogo de medios por municipio: la semilla curada a mano por Juli.

`data/raw/medios/medios_por_municipio.csv` es un relevamiento manual de los
medios de cada uno de los 86: el oficial (del municipio) y los alternativos
(diarios, radios y portales locales). No hay ninguna fuente automatica que
sepa esto, asi que la semilla es un activo y se versiona.

Tres cosas que se corrigen al leerla, todas verificadas contra el archivo:

1. **La columna ID_Municipios esta corrida.** Los 86 nombres matchean el Gold
   Standard, pero 46 de las filas traen un id que no corresponde: el archivo da
   MUN-BA-041 para Pinamar y el Gold Standard dice MUN-BA-042, y de ahi en
   adelante esta desplazado uno. **El cruce se hace por NOMBRE y el id sale del
   Gold Standard.** Cruzar por el id del archivo le daria a 46 municipios los
   medios del vecino, que es el mismo error que las poblaciones cruzadas del
   Gold Standard (handoff §5.1).

2. **Dos entradas no son medios periodisticos.** "Tapalqué SIBOM" es el boletin
   oficial y "General Belgrano Gobierno Municipal" es el canal del municipio
   repetido en la columna de alternativos. Se reclasifican: un canal oficial no
   puede contarse como cobertura independiente.

3. **"InfoZona" figura escrito de dos formas.** Se unifica, porque si no el
   mismo medio contaria como dos.
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, NamedTuple

_AQUI = Path(__file__).resolve().parent
PROJECT_ROOT = _AQUI.parents[1]
if str(PROJECT_ROOT / "src" / "discovery") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src" / "discovery"))

SEMILLA = PROJECT_ROOT / "data" / "raw" / "medios" / "medios_por_municipio.csv"

# Entradas de la columna "alternativos" que en realidad son canales oficiales.
# Un canal del municipio no es cobertura independiente: si se contara como
# alternativo, un municipio sin prensa propia pareceria tener quien lo controle.
NO_SON_MEDIOS = {
    "General Belgrano Gobierno Municipal",
    "Tapalqué SIBOM",
}


class Medio(NamedTuple):
    nombre: str
    municipio: str
    id_municipio: str
    # oficial = del municipio; alternativo = diario, radio o portal independiente
    tipo: str


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t)


def _partes(campo: str) -> List[str]:
    return [n.strip() for n in (campo or "").split(",") if n.strip()]


def leer(path: Path = SEMILLA) -> List[Medio]:
    """Todos los medios de la semilla, ya limpios y con el id correcto."""
    from discovery_engine import cargar_municipios

    ids = {m.nombre: m.id_municipio for m in cargar_municipios()}

    # nombre normalizado -> forma canonica, para que "InfoZona" e "Infozona"
    # sean el mismo medio y no dos.
    canonico: Dict[str, str] = {}
    salida: List[Medio] = []

    with open(path, encoding="utf-8-sig", newline="") as fh:
        for fila in csv.DictReader(fh):
            municipio = (fila.get("Municipios") or "").strip()
            id_municipio = ids.get(municipio)
            if id_municipio is None:
                # Un municipio que no es de los 86 no entra: el relevamiento son
                # 86 y meter otro romperia los cruces.
                continue

            for nombre in _partes(fila.get("Medios_Oficial")):
                salida.append(Medio(nombre, municipio, id_municipio, "oficial"))

            for nombre in _partes(fila.get("Medios_Alternativos")):
                tipo = "oficial" if nombre in NO_SON_MEDIOS else "alternativo"
                clave = _normalizar(nombre)
                nombre = canonico.setdefault(clave, nombre)
                salida.append(Medio(nombre, municipio, id_municipio, tipo))

    return salida


def por_municipio(medios: List[Medio] = None) -> Dict[str, List[Medio]]:
    salida: Dict[str, List[Medio]] = {}
    for m in medios if medios is not None else leer():
        salida.setdefault(m.municipio, []).append(m)
    return salida


def regionales(medios: List[Medio] = None, minimo: int = 2) -> Dict[str, List[str]]:
    """Medios que cubren mas de un municipio.

    Importan por dos razones opuestas. A favor: uno solo aporta cobertura a
    varios partidos, asi que rinde. En contra: al contar hechos hay que evitar
    sumar la misma nota en dos municipios.

    Ojo con la semilla: da InfoZona en 3 municipios, pero Juli dice que cubre mas
    de 20. La lista es un punto de partida, no el mapa completo de la cobertura.
    """
    cuenta: Dict[str, List[str]] = {}
    for m in medios if medios is not None else leer():
        if m.tipo == "alternativo":
            cuenta.setdefault(m.nombre, []).append(m.municipio)
    return {n: sorted(ms) for n, ms in cuenta.items() if len(ms) >= minimo}


__all__ = ["Medio", "NO_SON_MEDIOS", "SEMILLA", "leer", "por_municipio", "regionales"]
