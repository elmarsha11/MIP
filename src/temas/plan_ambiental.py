"""
Importa el relevamiento ambiental manual de los 86 municipios.

Es la mejor fuente que tiene MIP sobre el tema: relevamiento humano, completo
—86 de 86, sin una celda vacia— y con las fuentes oficiales de cada fila. Por eso
manda sobre lo que saque el motor de temas: eso es lectura de un modelo, esto es
trabajo verificado.

    python src/temas/plan_ambiental.py --importar
    python src/temas/plan_ambiental.py --ficha Navarro
    python src/temas/plan_ambiental.py --resumen

El CSV crudo se versiona tal cual esta en data/raw/ambiental/. La reparacion es
codigo, no una edicion a mano del archivo: asi es auditable, testeable, y volver
a exportar el original no obliga a rehacer el arreglo.

El bug del CSV
--------------
Todas las filas traen 19 campos y la cabecera nombra 10. Los campos con comas
salieron **sin comillas**, asi que una lista como "industrias lactea, quesera,
agroindustrial y metalmecanica liviana" se partio en cuatro campos y corrio todo
lo de la derecha. En Suipacha eso dejaba los Puntos Verdes bajo el titulo
"Fuentes Oficiales", que en realidad era la columna de GIRSU desplazada.

Se repega con dos senales, y ninguna sola alcanza:

1. Si un campo no cierra oracion, el siguiente es su continuacion.
2. Si un campo empieza en minuscula, es continuacion del anterior.

La segunda existe por Ayacucho: su campo de fiscalizacion termina en
"(Mateo Hermanos S.A.)", que parece cierre de oracion y no lo es. La primera
existe porque las URLs empiezan en minuscula y no son continuacion de nada.

Con las dos, las 86 filas reconstruyen a exactamente 6 campos y las 86 tienen
URL en el sexto. Son dos invariantes independientes: si alguna vez fallan, el
importador se planta en vez de guardar datos corridos.
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence

_AQUI = Path(__file__).resolve().parent
_SRC = _AQUI.parent
PROJECT_ROOT = _SRC.parent
for _ruta in (_AQUI, _SRC / "extraction", _SRC / "discovery"):
    if str(_ruta) not in sys.path:
        sys.path.insert(0, str(_ruta))

from modelos import normalizar_para_cotejo  # noqa: E402

CSV_CRUDO = PROJECT_ROOT / "data" / "raw" / "ambiental" / "plan_ambiental_86.csv"
DIR_SALIDA = PROJECT_ROOT / "data" / "processed" / "temas"
SQLITE_TEMAS = DIR_SALIDA / "temas_86.sqlite"

# Las seis columnas de contenido, en orden. El orden ES el contrato: despues de
# reparar, la posicion define la categoria.
CATEGORIAS = (
    "promotores_ambientales",
    "fiscalizacion_3ra",
    "girsu_residuos",
    "areas_arbolado",
    "otras_acciones",
)
COLUMNA_FUENTES = 5  # la sexta

ETIQUETAS = {
    "promotores_ambientales": "Promotores ambientales",
    "fiscalizacion_3ra": "Fiscalizacion 3ra categoria",
    "girsu_residuos": "GIRSU y residuos",
    "areas_arbolado": "Areas protegidas y arbolado",
    "otras_acciones": "Otras acciones ambientales",
}

# Nombres que el CSV escribe distinto que el resto del sistema. Sin esto el join
# pierde cinco municipios en silencio, que es la peor forma de perderlos.
ALIAS = {
    "leandro n. alem": "Alem",
    "gonzales chaves": "Gonzales Cháves",
    "maipú": "Maipu",
    "saavedra (pigüé)": "Saavedra",
    "tapalqué": "Tapalque",
}

DDL = """
CREATE TABLE IF NOT EXISTS plan_ambiental (
    municipio TEXT NOT NULL,
    id_municipio TEXT NOT NULL,
    seccion TEXT,
    poblacion INTEGER,
    categoria TEXT NOT NULL,
    texto TEXT NOT NULL,
    estado TEXT,
    fuentes TEXT NOT NULL,
    origen TEXT NOT NULL DEFAULT 'manual',
    PRIMARY KEY (municipio, categoria)
);
CREATE INDEX IF NOT EXISTS idx_pa_categoria ON plan_ambiental(categoria);
CREATE INDEX IF NOT EXISTS idx_pa_estado ON plan_ambiental(categoria, estado);
"""


# ---------------------------------------------------------------------------
# Reparacion del CSV
# ---------------------------------------------------------------------------


class FilaMalformada(ValueError):
    """El CSV no reconstruye. Mejor plantarse que guardar datos corridos."""


def _cierra_oracion(texto: str) -> bool:
    return bool(re.search(r"[.!?][\"'’\)\]]?\s*$", texto.strip()))


def _es_url(texto: str) -> bool:
    return bool(re.match(r"(https?://|www\.)", texto.strip()))


def _es_continuacion(texto: str) -> bool:
    """Un campo que arranca en minuscula viene partido del anterior.

    Las URLs quedan afuera: empiezan en minuscula y no continuan nada.
    """
    limpio = texto.strip()
    return bool(limpio) and limpio[0].islower() and not _es_url(limpio)


def reparar_campos(campos: Sequence[str]) -> List[str]:
    """Re-pega los fragmentos que una coma sin comillas separo."""
    piezas = [c.strip() for c in campos if c.strip()]
    if not piezas:
        return []
    salida = [piezas[0]]
    for pieza in piezas[1:]:
        if _es_url(pieza) and not _es_url(salida[-1]):
            # Una URL arranca la columna de fuentes, aunque el campo anterior
            # haya quedado sin punto final. Si el anterior YA es una URL, es la
            # segunda fuente de la misma celda y se pega.
            salida.append(pieza)
        elif _es_continuacion(pieza) or not _cierra_oracion(salida[-1]):
            salida[-1] += ", " + pieza
        else:
            salida.append(pieza)
    return salida


# ---------------------------------------------------------------------------
# Resumen derivado
# ---------------------------------------------------------------------------

_PROVINCIALES = ("ministerio de ambiente", "opds", "organismo provincial", "provincia")
_MUNICIPALES = ("el municipio", "municipal", "la municipalidad", "el distrito", "comuna")

# Senales por categoria. Cada una es una lectura DERIVADA del texto, no un dato
# nuevo: el texto viaja siempre al lado y es lo que manda. Sirven para que los 86
# se puedan comparar, que es justo lo que un parrafo en prosa no permite.
_SENALES: Dict[str, Sequence[tuple]] = {
    "girsu_residuos": (
        ("planta_propia", ("planta de tratamiento", "planta de separacion",
                           "planta de clasificacion", "planta municipal de recicl",
                           "planta de recicl")),
        ("puntos_verdes", ("punto verde", "puntos verdes", "punto limpio", "puntos limpios")),
    ),
    "areas_arbolado": (
        ("reserva_declarada", ("reserva natural", "parque nacional", "area protegida",
                               "reserva municipal")),
        ("plan_arbolado", ("arbolado",)),
    ),
    "promotores_ambientales": (
        ("cuerpo_nombrado", ("promotor", "promotora")),
    ),
    "otras_acciones": (
        ("ordenanza_fitosanitarios", ("fitosanitario", "agroquimico")),
    ),
}


def competencia_fiscalizacion(texto: str) -> str:
    """Quien ejerce el control de tercera categoria, segun lo que dice el texto.

    Es la unica categoria donde la pregunta tiene una respuesta de tres valores
    en vez de un si/no, y es la que mas importa: por Ley 11.459 el Certificado de
    Aptitud Ambiental lo emite la Provincia, asi que "provincial" no es una
    carencia del municipio sino como esta repartida la competencia.
    """
    plano = normalizar_para_cotejo(texto)
    provincial = any(p in plano for p in _PROVINCIALES)
    municipal = any(m in plano for m in _MUNICIPALES)
    if provincial and municipal:
        return "mixta"
    if provincial:
        return "provincial"
    if municipal:
        return "municipal"
    return "sin_clasificar"


def estado_derivado(categoria: str, texto: str) -> str:
    """Etiqueta comparable entre municipios. Nunca reemplaza al texto."""
    if categoria == "fiscalizacion_3ra":
        return competencia_fiscalizacion(texto)
    plano = normalizar_para_cotejo(texto)
    marcas = [
        nombre
        for nombre, patrones in _SENALES.get(categoria, ())
        if any(p in plano for p in patrones)
    ]
    return "+".join(marcas) if marcas else "sin_senal"


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


class FilaPlan(NamedTuple):
    municipio: str
    id_municipio: str
    seccion: str
    poblacion: Optional[int]
    textos: Dict[str, str]
    fuentes: str


def _entero(valor: str) -> Optional[int]:
    try:
        return int(re.sub(r"[^\d]", "", valor or "") or 0) or None
    except ValueError:
        return None


def leer(path: Path = CSV_CRUDO) -> List[FilaPlan]:
    """Lee el CSV crudo, lo repara y verifica los dos invariantes."""
    if not Path(path).exists():
        raise FileNotFoundError(f"No existe {path}")

    with open(path, encoding="utf-8-sig", newline="") as fh:
        crudo = list(csv.reader(fh))
    if len(crudo) < 2:
        raise FilaMalformada(f"{path} no tiene filas de datos")

    filas: List[FilaPlan] = []
    for numero, fila in enumerate(crudo[1:], start=2):
        if len(fila) < 5 or not (fila[1] or "").strip():
            continue
        reparada = reparar_campos(fila[4:])

        if len(reparada) != len(CATEGORIAS) + 1:
            raise FilaMalformada(
                f"linea {numero} ({fila[1]}): reconstruyo {len(reparada)} campos y "
                f"se esperaban {len(CATEGORIAS) + 1}. El CSV cambio de forma: "
                "revisar reparar_campos antes de importar."
            )
        if not re.search(r"https?://|www\.", reparada[COLUMNA_FUENTES]):
            raise FilaMalformada(
                f"linea {numero} ({fila[1]}): el ultimo campo no trae URL, asi que "
                "las columnas quedaron corridas."
            )

        nombre = (fila[1] or "").strip()
        filas.append(
            FilaPlan(
                municipio=ALIAS.get(nombre.lower(), nombre),
                id_municipio=(fila[0] or "").strip(),
                seccion=(fila[2] or "").strip(),
                poblacion=_entero(fila[3]),
                textos=dict(zip(CATEGORIAS, reparada[: len(CATEGORIAS)])),
                fuentes=reparada[COLUMNA_FUENTES],
            )
        )
    return filas


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------


def guardar(filas: Sequence[FilaPlan], path: Path = SQLITE_TEMAS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        con.execute("DELETE FROM plan_ambiental")
        for f in filas:
            for categoria in CATEGORIAS:
                texto = f.textos.get(categoria, "").strip()
                if not texto:
                    continue
                con.execute(
                    "INSERT OR REPLACE INTO plan_ambiental "
                    "(municipio, id_municipio, seccion, poblacion, categoria, "
                    " texto, estado, fuentes, origen) VALUES (?,?,?,?,?,?,?,?,'manual')",
                    (
                        f.municipio, f.id_municipio, f.seccion, f.poblacion,
                        categoria, texto, estado_derivado(categoria, texto), f.fuentes,
                    ),
                )
        con.commit()
    finally:
        con.close()
    return path


def importar(path_csv: Path = CSV_CRUDO, path_sqlite: Path = SQLITE_TEMAS) -> int:
    filas = leer(path_csv)
    guardar(filas, path_sqlite)
    return len(filas)


# ---------------------------------------------------------------------------
# Lectura humana
# ---------------------------------------------------------------------------


def ficha(municipio: str, path: Path = SQLITE_TEMAS) -> str:
    if not Path(path).exists():
        return "Todavia no se importo. Corre --importar."
    con = sqlite3.connect(path)
    try:
        filas = con.execute(
            "SELECT categoria, texto, estado, fuentes, seccion, poblacion "
            "FROM plan_ambiental WHERE municipio = ?",
            (municipio,),
        ).fetchall()
    finally:
        con.close()
    if not filas:
        return f"Sin datos de {municipio}."

    orden = {c: i for i, c in enumerate(CATEGORIAS)}
    filas.sort(key=lambda f: orden.get(f[0], 99))
    cab = filas[0]
    lineas = [f"{municipio} - Plan ambiental", f"Seccion {cab[4]} - {cab[5]:,} hab".replace(",", "."), "=" * 68]
    for categoria, texto, estado, *_ in filas:
        lineas.append("")
        lineas.append(f"{ETIQUETAS[categoria]}  [{estado}]")
        for i in range(0, len(texto), 76):
            lineas.append(f"   {texto[i:i + 76]}")
    lineas += ["", "Fuentes:", f"   {cab[3]}"]
    return "\n".join(lineas)


def resumen(path: Path = SQLITE_TEMAS) -> str:
    if not Path(path).exists():
        return "Todavia no se importo. Corre --importar."
    con = sqlite3.connect(path)
    try:
        total = con.execute("SELECT COUNT(DISTINCT municipio) FROM plan_ambiental").fetchone()[0]
        filas = con.execute(
            "SELECT categoria, estado, COUNT(*) FROM plan_ambiental GROUP BY 1,2"
        ).fetchall()
    finally:
        con.close()

    por_categoria: Dict[str, List[tuple]] = {}
    for categoria, estado, n in filas:
        por_categoria.setdefault(categoria, []).append((estado, n))

    lineas = [f"Plan ambiental - {total} municipios", "=" * 68]
    for categoria in CATEGORIAS:
        lineas.append("")
        lineas.append(ETIQUETAS[categoria])
        for estado, n in sorted(por_categoria.get(categoria, []), key=lambda x: -x[1]):
            lineas.append(f"   {estado:<34} {n:>3}")
    return "\n".join(lineas)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--importar", action="store_true")
    parser.add_argument("--ficha")
    parser.add_argument("--resumen", action="store_true")
    args = parser.parse_args(argv)

    if args.importar:
        n = importar()
        print(f"Importados {n} municipios a {SQLITE_TEMAS}")
        print()
        print(resumen())
        return 0
    if args.ficha:
        print(ficha(args.ficha))
        return 0
    if args.resumen:
        print(resumen())
        return 0
    parser.error("elegi --importar, --ficha o --resumen")
    return 2


if __name__ == "__main__":
    sys.exit(main())
