"""
Capa 2 - Fuente primaria: el propio sitio del municipio.

Dos pasos:

  1. descubrir_dominio_oficial(): prueba los patrones de dominio conocidos de los
     municipios de PBA por HTTP y se queda con el que responde 200 Y cuyo <title>
     dice ser la municipalidad de ese municipio. La evidencia es el titulo real
     de la pagina, no una suposicion.

  2. cosechar_links(): una vez que se sabe cual es el sitio, se leen los enlaces
     de su home y se tipifican. El menu de un municipio es exactamente lo que un
     investigador miraria a mano: Tramites, Transparencia, Salud, Tasas, Reclamos.

Por que esto y no solo el buscador (HANDOFF Capa 2): los buscadores publicos
cortan por rate limit mucho antes de las 688 queries que exigen 86 municipios,
y cuando cortan no devuelven nada. El sitio del municipio, en cambio, es una
fuente de primera mano, sin intermediario y sin cuota. El buscador queda como
fuente complementaria para los municipios cuyo dominio no se puede adivinar.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

try:  # ejecutado como paquete
    from .schemas import (
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        ahora_iso,
        normalizar_slug,
        normalizar_texto,
        variantes_slug,
    )
    from .search_provider import clasificar_tipo, es_dominio_descartable
    from .validator import consultar, titulo_es_del_municipio
except ImportError:  # ejecutado como script
    from schemas import (  # type: ignore[no-redef]
        Confianza,
        DiscoveryURL,
        EstadoValidacion,
        TipoURL,
        ahora_iso,
        normalizar_slug,
        normalizar_texto,
        variantes_slug,
    )
    from search_provider import clasificar_tipo, es_dominio_descartable  # type: ignore[no-redef]
    from validator import consultar, titulo_es_del_municipio  # type: ignore[no-redef]

from bs4 import BeautifulSoup

# Patrones de dominio observados en los 86 municipios del Gold Standard.
# El orden importa: el primero que valida gana.
PATRONES_DOMINIO: Sequence[str] = (
    "{slug}.gob.ar",
    "www.{slug}.gob.ar",
    "{slug}.gov.ar",
    "www.{slug}.gov.ar",
    "muni{slug}.gob.ar",
    "muni{slug}.gov.ar",
    "municipio{slug}.gob.ar",
    "municipalidad{slug}.gob.ar",
    "municipalidadde{slug}.gob.ar",
    "{slug}.mun.gba.gov.ar",
)

# Provincias distintas de Buenos Aires. Hay municipios homonimos en varias
# (25 de Mayo, Maipu, Rivadavia, Colon, Castelli, General Alvear...), y un sitio
# de otra provincia pasaria el chequeo de titulo sin problema. ADR-0009: asignar
# el municipio equivocado es peor que no encontrar nada.
PROVINCIAS_AJENAS = (
    "mendoza", "entre rios", "cordoba", "santa fe", "corrientes", "san juan",
    "san luis", "salta", "jujuy", "chaco", "formosa", "misiones", "neuquen",
    "rio negro", "chubut", "santa cruz", "tierra del fuego", "la pampa",
    "la rioja", "catamarca", "tucuman", "santiago del estero",
)

MAX_LINKS_COSECHADOS = 40
TIMEOUT_DOMINIO = 20  # hay portales municipales muy lentos (Balcarce tarda >15s)
WORKERS_DOMINIO = 9
REINTENTOS_REGISTRO = 3  # los portales municipales lentos merecen mas de una chance

# Secciones que se repiten en todos los portales y no aportan como URL tipificada.
PATHS_IGNORADOS = (
    "/wp-content/", "/wp-admin/", "/wp-json/", "/feed", ".jpg", ".png", ".pdf?",
    "/tag/", "/category/", "/author/", "javascript:", "mailto:", "tel:",
)


class DominioOficial(NamedTuple):
    url: str  # home final tras redirects
    titulo: str  # <title> real de la pagina
    patron: str  # patron que lo encontro (trazabilidad)
    # True  = el <title> de la pagina acredita al municipio -> confianza Alta.
    # False = lo acredita un registro provincial, no la pagina -> confianza Media.
    #         Pasa con sitios cuyo titulo no se nombra a si mismo como municipalidad
    #         ("Gesell, cada vez mejor", "Monte Hermoso sitio oficial").
    acreditado_por_titulo: bool = True


def _slug(municipio: str) -> str:
    return normalizar_slug(municipio)


def candidatos_dominio(municipio: str, esquema: str = "https") -> List[Tuple[str, str]]:
    """(url, patron) a probar, en orden de preferencia.

    El nombre completo va antes que el corto: 'generalvillegas.gob.ar' se prueba
    antes que 'villegas.gob.ar'.
    """
    candidatos: List[Tuple[str, str]] = []
    vistos = set()
    for slug in variantes_slug(municipio):
        for patron in PATRONES_DOMINIO:
            host = patron.format(slug=slug)
            url = f"{esquema}://{host}/"
            if url in vistos:
                continue
            vistos.add(url)
            candidatos.append((url, host))
    return candidatos


def _host_nombra_al_municipio(url: str, municipio: str) -> bool:
    """El dominio lleva el nombre del municipio y es un dominio de gobierno."""
    host = normalizar_slug((urlparse(url).hostname or ""))
    if not any(v and v in host for v in variantes_slug(municipio)):
        return False
    return any(
        (urlparse(url).hostname or "").lower().endswith(s) for s in (".gob.ar", ".gov.ar")
    )


def _variantes_de_esquema(url: str) -> List[str]:
    """https primero, http despues. Nunca al reves, y nunca solo uno.

    Forzar https rompe los municipios que no tienen TLS; quedarse en http
    desaprovecha a los que si lo tienen. Se prueban los dos, en ese orden.
    """
    limpia = url.strip()
    sin_esquema = limpia.split("://", 1)[-1]
    return [f"https://{sin_esquema}", f"http://{sin_esquema}"]


# Marcas de que un sitio es bonaerense: la provincia, su agencia de recaudacion,
# su sistema de boletines o sus dominios.
SENALES_BUENOS_AIRES = ("buenos aires", "arba", "sibom", "gba.gob.ar", "gba.gov.ar", "bonaerense")

# Menciones sueltas necesarias para descartar un sitio sin ninguna senal
# bonaerense. Una sola suele ser un nombre de calle: el sitio de Carlos Casares
# es bonaerense y nombra a 'Neuquen' una sola vez.
MIN_MENCIONES_AJENAS = 2


def provincia_ajena(texto: str) -> Optional[str]:
    """Devuelve la provincia ajena que evidencia el texto, o None.

    Existe porque hay municipios homonimos en varias provincias y el chequeo de
    titulo no los distingue: 'Municipalidad de Maipu' es valido en Buenos Aires
    y en Mendoza, y 'Municipalidad de Rivadavia' en Buenos Aires y en San Juan.

    Tres senales, de mas fuerte a mas debil:
      1. "Provincia de San Juan"           -> lo dice la pagina
      2. "Rivadavia, San Juan, Argentina"  -> el domicilio de contacto
      3. dos o mas menciones sueltas y ninguna marca bonaerense

    Verificado el 2026-08-07 contra 9 sitios reales (5 bonaerenses, 3 de otras
    provincias, 1 dudoso): 9 aciertos. Varios sitios bonaerenses legitimos no
    nombran nunca a la provincia, por eso la ausencia de marca no basta para
    descartar.
    """
    import re

    normalizado = normalizar_texto(texto)

    for provincia in PROVINCIAS_AJENAS:
        if re.search(rf"provincia de {provincia}\b", normalizado):
            return provincia
        if re.search(rf"\b{provincia},\s*(republica argentina|argentina)\b", normalizado):
            return provincia

    if any(senal in normalizado for senal in SENALES_BUENOS_AIRES):
        return None

    for provincia in PROVINCIAS_AJENAS:
        if len(re.findall(rf"\b{provincia}\b", normalizado)) >= MIN_MENCIONES_AJENAS:
            return provincia
    return None


def descubrir_dominio_oficial(
    municipio: str,
    timeout: int = TIMEOUT_DOMINIO,
    candidatos_extra: Sequence[str] = (),
) -> Optional[DominioOficial]:
    """Prueba los patrones en paralelo y devuelve el primero que se acredita.

    Acreditarse = responder <400 y que el <title> nombre al municipio junto a
    'municipalidad'/'municipio'/'gobierno'. Un 200 solo no alcanza: hay dominios
    parkeados que responden 200 con publicidad.

    candidatos_extra va primero: son URLs que ya publico un registro oficial
    (ej: el enlace al sitio municipal en la ficha SIBOM), asi que valen mas que
    cualquier patron adivinado.
    """
    # Las pistas de registros van primero (https y http de cada una), despues los
    # patrones adivinados: primero toda la tanda https, y solo si nada acredita,
    # la tanda http. Asi no se paga el doble de pedidos en los ~75 municipios que
    # si tienen TLS.
    pistas: List[Tuple[str, str, bool]] = []
    for pista in [u for u in candidatos_extra if u]:
        for variante in _variantes_de_esquema(pista):
            pistas.append((variante, f"registro:{variante}", True))

    def _acreditar(tanda: List[Tuple[str, str, bool]]) -> Optional[DominioOficial]:
        def _probar(item: Tuple[str, str, bool]) -> Optional[DominioOficial]:
            url, patron, de_registro = item
            resp = consultar(url, timeout=timeout)
            # Vale la pena insistir: esta URL la publica un registro oficial y
            # varios portales municipales responden de forma intermitente
            # (Balcarce, Rauch, Tapalque). Un solo fallo no prueba que no exista,
            # y darlo por muerto borraria un municipio que si tiene sitio.
            for _ in range(REINTENTOS_REGISTRO if de_registro else 0):
                if resp.status is not None and resp.titulo:
                    break
                resp = consultar(url, timeout=timeout)
            if resp.status is None or resp.status >= 400 or not resp.titulo:
                return None
            acredita_titulo = titulo_es_del_municipio(resp.titulo, municipio)
            # Un patron adivinado necesita acreditarse. Se acepta sin titulo
            # acreditante solo si el host lleva el nombre del municipio y es un
            # dominio oficial: ahi decide el cuerpo de la pagina, mas abajo.
            # (dorrego.gob.ar se titula "M.C.D. - Sitio Oficial" y es Coronel Dorrego.)
            if not acredita_titulo and not de_registro and not _host_nombra_al_municipio(
                resp.url_final, municipio
            ):
                return None
            return DominioOficial(
                url=resp.url_final.split("#")[0],
                titulo=resp.titulo,
                patron=patron,
                acreditado_por_titulo=acredita_titulo,
            )

        with ThreadPoolExecutor(max_workers=WORKERS_DOMINIO) as pool:
            resultados = list(pool.map(_probar, tanda))

        for (_, _, de_registro), encontrado in zip(tanda, resultados):
            if encontrado is None:
                continue
            if de_registro:
                return encontrado

            cuerpo = consultar_html(encontrado.url) or encontrado.titulo
            # Un dominio adivinado puede ser el homonimo de otra provincia.
            ajena = provincia_ajena(cuerpo)
            if ajena:
                print(
                    f"    [descartado] {encontrado.url} parece de {ajena.title()}, "
                    f"no de Buenos Aires (municipio homonimo)"
                )
                continue
            if encontrado.acreditado_por_titulo:
                return encontrado
            # El titulo no acredita: que lo acredite el cuerpo de la pagina.
            if titulo_es_del_municipio(cuerpo, municipio):
                return encontrado
            print(
                f"    [descartado] {encontrado.url} no se acredita como "
                f"{municipio}: ni el titulo ni el contenido lo nombran"
            )
        return None

    tandas = [
        pistas + [(u, p, False) for u, p in candidatos_dominio(municipio, "https")],
        [(u, p, False) for u, p in candidatos_dominio(municipio, "http")],
    ]
    for tanda in tandas:
        encontrado = _acreditar(tanda)
        if encontrado is not None:
            return encontrado
    return None


def cosechar_links(
    dominio: DominioOficial,
    municipio: str,
    id_municipio: str,
    fecha: Optional[str] = None,
    maximo: int = MAX_LINKS_COSECHADOS,
) -> List[DiscoveryURL]:
    """Lee la home del municipio y tipifica sus enlaces internos.

    La evidencia de cada URL es el texto del enlace mas el titulo de la home:
    'el sitio oficial de X enlaza esto como "Tramites y Servicios"'. Es evidencia
    de primera mano y verificable. La Capa 3 despues la reemplaza por el <title>
    real de la pagina destino.
    """
    fecha = fecha or ahora_iso()
    html = consultar_html(dominio.url)
    if not html:
        return []

    sopa = BeautifulSoup(html, "html.parser")
    host = (urlparse(dominio.url).hostname or "").lower()

    urls: List[DiscoveryURL] = []
    vistas = set()
    for ancla in sopa.find_all("a", href=True):
        if len(urls) >= maximo:
            break
        href = ancla["href"].strip()
        if any(p in href.lower() for p in PATHS_IGNORADOS):
            continue
        destino = urljoin(dominio.url, href).split("#")[0]
        # Se conserva el esquema del propio sitio: si el municipio no tiene TLS,
        # sus enlaces internos tampoco (ADR-0012).
        if not destino.startswith(("https://", "http://")):
            continue
        if (urlparse(destino).hostname or "").lower() != host:
            continue  # solo el propio sitio; lo externo lo trae el buscador
        if es_dominio_descartable(destino):
            continue

        clave = destino.rstrip("/").lower()
        if clave in vistas:
            continue

        tipo = clasificar_tipo(destino)
        if tipo is TipoURL.OTRO:
            continue  # sin tipo no aporta al inventario

        texto = " ".join(ancla.get_text(" ", strip=True).split())[:120]
        if not texto:
            continue

        vistas.add(clave)
        evidencia = f'"{texto}" - enlace en {dominio.titulo}'[:500]
        try:
            urls.append(
                DiscoveryURL(
                    municipio=municipio,
                    id_municipio=id_municipio,
                    url=destino,
                    tipo=tipo,
                    fuente_query=f"sitio_oficial:{dominio.url}",
                    titulo_fragmento=evidencia,
                    fecha_descubrimiento=fecha,
                    confianza=Confianza.MEDIA,
                    estado_validacion=EstadoValidacion.PENDIENTE,
                    es_oficial=True,  # esta enlazado desde el sitio acreditado
                )
            )
        except ValueError:
            continue
    return urls


def consultar_html(url: str, timeout: int = 20) -> Optional[str]:
    """GET que devuelve el HTML crudo (consultar() solo devuelve el titulo)."""
    try:  # import local para no crear dependencia circular en tiempo de carga
        from .validator import _sesion, MAX_BYTES_HTML  # type: ignore
    except ImportError:
        from validator import _sesion, MAX_BYTES_HTML  # type: ignore

    import requests

    try:
        resp = _sesion().get(url, timeout=timeout, allow_redirects=True, stream=True)
        contenido = resp.raw.read(MAX_BYTES_HTML, decode_content=True) or b""
        resp.close()
        if resp.status_code >= 400:
            return None
        encoding = resp.encoding or resp.apparent_encoding or "utf-8"
        return contenido.decode(encoding, errors="replace")
    except requests.RequestException:
        return None


def descubrir_sitio(
    municipio: str,
    id_municipio: str,
    fecha: Optional[str] = None,
    candidatos_extra: Sequence[str] = (),
) -> List[DiscoveryURL]:
    """Capa 2 primaria completa: dominio oficial + cosecha de su home."""
    fecha = fecha or ahora_iso()
    dominio = descubrir_dominio_oficial(municipio, candidatos_extra=candidatos_extra)
    if dominio is None:
        return []

    if dominio.acreditado_por_titulo:
        fragmento = dominio.titulo
        confianza = Confianza.ALTA  # responde 200 y el <title> acredita al municipio
    else:
        # La pagina no se nombra a si misma como municipalidad; quien la acredita
        # es el registro provincial. Se deja constancia de eso en la evidencia y
        # la confianza queda en Media (ADR-0009: no afirmamos mas de lo que probamos).
        fragmento = f"{dominio.titulo} - publicado como sitio oficial de {municipio} por el SIBOM"
        confianza = Confianza.MEDIA

    campos = dict(
        municipio=municipio,
        id_municipio=id_municipio,
        url=dominio.url,
        tipo=TipoURL.SITIO_OFICIAL,
        fuente_query=f"heuristica_dominio:{dominio.patron}",
        titulo_fragmento=fragmento[:500],
        fecha_descubrimiento=fecha,
        estado_validacion=EstadoValidacion.VALIDADA,
        es_oficial=True,
    )
    try:
        home = DiscoveryURL(confianza=confianza, **campos)
    except ValueError:
        # No llega a Alta segun el schema. Se degrada, nunca se descarta el sitio
        # entero: encontrarlo con menos confianza sigue siendo encontrarlo.
        home = DiscoveryURL(confianza=Confianza.MEDIA, **campos)

    return [home] + cosechar_links(dominio, municipio, id_municipio, fecha=fecha)


__all__ = [
    "MAX_LINKS_COSECHADOS",
    "PATRONES_DOMINIO",
    "DominioOficial",
    "candidatos_dominio",
    "consultar_html",
    "cosechar_links",
    "descubrir_dominio_oficial",
    "descubrir_sitio",
]
