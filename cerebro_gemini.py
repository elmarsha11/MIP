import json
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from bs4 import BeautifulSoup
from google import genai

# ==========================================
# 1. CONFIGURACIÓN Y RUTAS
# ==========================================
RUTA_ACTUAL = os.path.dirname(os.path.abspath(__file__))
RUTA_CREDENCIAL = os.path.join(RUTA_ACTUAL, "credenciales.txt")

# Apuntamos directamente a tu nuevo archivo CSV local
RUTA_CSV = os.path.join(RUTA_ACTUAL, "TRANSFORMACION.csv")
RUTA_PROGRESS_JSON = os.path.join(RUTA_ACTUAL, "progreso_municipios.json")

MODELO_GEMINI = "gemini-2.5-flash"

MAX_MUNICIPIOS_EN_PARALELO = 3
GEMINI_RPM_MAX = 10
GEMINI_RPD_MAX = 250

TIMEOUT_PORTAL = 12
MAX_CHARS_PORTAL = 3500

candado_json = threading.Lock()
candado_print = threading.Lock()


def log(municipio, mensaje):
    with candado_print:
        print(f"[{municipio}] {mensaje}")


# ==========================================
# 2. ESQUEMA DE DATOS Y RATE LIMITER
# ==========================================
ESQUEMA_RESPUESTA_MUNICIPIO = {
    "type": "object",
    "properties": {
        "tramites_digitales": {
            "type": "string",
            "description": "Resumen de trámites o guía online disponible",
        },
        "salud": {
            "type": "string",
            "description": "Hospitales, CAPS o turnos médicos online",
        },
        "educacion": {
            "type": "string",
            "description": "Centros de desarrollo, CICs o programas educativos",
        },
        "medioambiente": {
            "type": "string",
            "description": "Reciclaje, puntos verdes u ordenanzas ambientales",
        },
        "seguridad": {
            "type": "string",
            "description": "Centro de monitoreo, botones antipánico o alertas",
        },
        "app_municipal": {
            "type": "boolean",
            "description": "True solo si se detecta app móvil oficial activa",
        },
        "transparencia": {
            "type": "string",
            "description": "Boletín oficial, portal de Gobierno Abierto o presupuestos",
        },
    },
    "required": [
        "tramites_digitales",
        "salud",
        "educacion",
        "medioambiente",
        "seguridad",
        "app_municipal",
        "transparencia",
    ],
}


class RateLimiterGemini:
    def __init__(self, rpm_max, rpd_max):
        self.rpm_max = rpm_max
        self.rpd_max = rpd_max
        self._marcas = deque()
        self._contador_dia = 0
        self._dia_actual = time.strftime("%Y-%m-%d")
        self._lock = threading.Lock()

    def esperar_turno(self):
        with self._lock:
            hoy = time.strftime("%Y-%m-%d")
            if hoy != self._dia_actual:
                self._dia_actual = hoy
                self._contador_dia = 0

            if self._contador_dia >= self.rpd_max:
                raise RuntimeError("Límite diario de Gemini alcanzado.")

            ahora = time.time()
            while self._marcas and ahora - self._marcas[0] > 60:
                self._marcas.popleft()

            if len(self._marcas) >= self.rpm_max:
                espera = 60 - (ahora - self._marcas[0]) + 0.5
                if espera > 0:
                    time.sleep(espera)
                ahora = time.time()
                while self._marcas and ahora - self._marcas[0] > 60:
                    self._marcas.popleft()

            self._marcas.append(time.time())
            self._contador_dia += 1


# ==========================================
# 3. EXTRACCIÓN Y ANÁLISIS
# ==========================================
def obtener_contenido_portal(nombre_muni):
    """Intenta buscar y raspar el portal del municipio."""
    slug = (
        nombre_muni.lower()
        .replace(" ", "")
        .replace("9dejulio", "9dejulio")
        .replace("ñ", "n")
    )
    url_tentativa = f"https://www.municipio{slug}.gob.ar"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }
    try:
        resp = requests.get(url_tentativa, timeout=TIMEOUT_PORTAL, headers=headers)
        resp.raise_for_status()
        sopa = BeautifulSoup(resp.text, "html.parser")

        # Limpiamos basura del HTML
        for tag in sopa(["script", "style", "nav", "footer"]):
            tag.decompose()

        texto = sopa.get_text(separator=" ", strip=True)
        return texto[:MAX_CHARS_PORTAL]
    except Exception:
        return None


def analizar_municipio(client, limiter, texto_portal, nombre_muni):
    prompt = f"""
    Sos un auditor de transformación digital de FRICDe. 
    Analizá el siguiente texto extraído del portal oficial del municipio de '{nombre_muni}'.
    Estructurá la información existente para los ejes del proyecto.
    Si algún eje no menciona datos claros en el texto, respondé "Sin datos informados".

    TEXTO DEL PORTAL:
    {texto_portal}
    """
    limiter.esperar_turno()
    respuesta = client.models.generate_content(
        model=MODELO_GEMINI,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": ESQUEMA_RESPUESTA_MUNICIPIO,
        },
    )
    return json.loads(respuesta.text)


def procesar_municipio(nombre_muni, client, limiter, progreso):
    if nombre_muni in progreso:
        log(nombre_muni, "⏩ Omitido (ya completado en checkpoint).")
        return

    log(nombre_muni, "🔎 Auditando portal municipal...")
    texto = obtener_contenido_portal(nombre_muni)

    if not texto:
        log(
            nombre_muni,
            "⚠️ No se pudo acceder al portal oficial. Registrando como sin datos.",
        )
        resultado = {
            "tramites_digitales": "Portal no accesible",
            "salud": "Portal no accesible",
            "educacion": "Portal no accesible",
            "medioambiente": "Portal no accesible",
            "seguridad": "Portal no accesible",
            "app_municipal": False,
            "transparencia": "Portal no accesible",
        }
    else:
        try:
            resultado = analizar_municipio(client, limiter, texto, nombre_muni)
        except Exception as e:
            log(nombre_muni, f"❌ Error en llamada API Gemini: {e}")
            return

    # Guardado incremental idempotente
    with candado_json:
        progreso[nombre_muni] = resultado
        with open(RUTA_PROGRESS_JSON, "w", encoding="utf-8") as f:
            json.dump(progreso, f, ensure_ascii=False, indent=2)

    log(nombre_muni, "✅ Procesado y guardado en JSON.")


# ==========================================
# 4. MAIN Y ENSAMBLADO FINAL
# ==========================================
def main():
    # 1. Primero buscamos y definimos la llave (key)
    try:
        with open(RUTA_CREDENCIAL, "r") as f:
            key = f.read().strip()
    except FileNotFoundError:
        print("❌ Fallo: No encuentro credenciales.txt.")
        return

    # 2. Inicializamos el cliente de Gemini usando esa llave
    client = genai.Client(api_key=key)

    # 3. Leemos el CSV con la degradación elegante para Windows
    try:
        df = pd.read_csv(RUTA_CSV, encoding="utf-8")
    except UnicodeDecodeError:
        print("⚠️ Codificación de Windows detectada. Adaptando lectura a latin1...")
        df = pd.read_csv(RUTA_CSV, encoding="latin1", sep=None, engine="python")
    except FileNotFoundError:
        print(f"❌ Fallo: No encuentro el archivo {RUTA_CSV}.")
        return

    # 4. Cargamos el progreso previo si el script se cortó antes
    progreso = {}
    if os.path.exists(RUTA_PROGRESS_JSON):
        with open(RUTA_PROGRESS_JSON, "r", encoding="utf-8") as f:
            progreso = json.load(f)

    limiter = RateLimiterGemini(GEMINI_RPM_MAX, GEMINI_RPD_MAX)

    print(f"🚀 Iniciando pipeline para {len(df)} municipios...\n")

    # 5. Ejecutamos los hilos en paralelo
    with ThreadPoolExecutor(max_workers=MAX_MUNICIPIOS_EN_PARALELO) as executor:
        futuros = [
            executor.submit(procesar_municipio, muni, client, limiter, progreso)
            for muni in df["Municipio"]
        ]
        for futuro in as_completed(futuros):
            futuro.result()

    # 6. Re-ensamblamos el CSV original
    print("\n📊 Impactando los resultados en el CSV local...")
    for idx, fila in df.iterrows():
        muni = fila["Municipio"]
        if muni in progreso:
            datos = progreso[muni]
            df.at[idx, "Trámites digitales"] = datos["tramites_digitales"]
            df.at[idx, "Salud"] = datos["salud"]
            df.at[idx, "Educación"] = datos["educacion"]
            df.at[idx, "Medioambiente"] = datos["medioambiente"]
            df.at[idx, "Seguridad"] = datos["seguridad"]
            df.at[idx, "App Municipal"] = "Si" if datos["app_municipal"] else "No"
            df.at[idx, "Transparencia"] = datos["transparencia"]

    # Guardamos en CSV con BOM para que Excel no rompa la codificación
    df.to_csv(RUTA_CSV, index=False, encoding="utf-8-sig")
    print("🏁 Proceso finalizado. Archivo CSV actualizado correctamente.")

if __name__ == "__main__":
    main()