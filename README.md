# MIP - Municipal Intelligence Platform

MIP (Municipal Intelligence Platform) es una plataforma de inteligencia territorial diseñada para descubrir, estructurar, validar y mantener actualizada la información pública de los municipios, transformando información dispersa en conocimiento verificable para apoyar la toma de decisiones.

## 🎯 ¿Qué es MIP?

*   **SÍ ES:** Un motor de adquisición de conocimiento. Un sistema que investiga a nivel municipal y territorial: encuentra fuentes oficiales donde estén (web oficial, redes sociales, boletín oficial, PDF de presupuesto, Google Play, etc.), extrae texto limpio, contrasta, valida y deja trazabilidad completa de cada dato.
*   **NO ES:** Un simple scraper, un ETL de Excel a Excel, un dashboard, o una simple herramienta transaccional. Esas son solo técnicas o consecuencias.

## 💡 El Problema

El problema principal no es la falta de información municipal, sino que esa información es **imposible de usar**. 
Entender un municipio del interior bonaerense (y de otras regiones) exige hoy un trabajo manual, lento y no reproducible. Esto se debe a tres capas problemáticas:

1.  **Parálisis Institucional:** Desfase tecnológico y fragmentación en los procesos municipales.
2.  **Fragmentación Informacional:** Información dispersa (webs, Facebook, boletines, etc.), sin estándar, volátil y engañosa.
3.  **Ceguera para decidir:** Sin información comparable y verificable es imposible planificar inversión pública, acceder a créditos o diseñar estrategias efectivas. El investigador hoy hace arqueología manual en múltiples plataformas.

MIP viene a automatizar este trabajo, convirtiendo información incierta en una **Single Source of Truth (SSOT)** (única fuente de verdad) estructurada.

## 🚀 Objetivos

*   **Motor Investigador Automático:** Reemplazar el trabajo manual por un agente que descubra fuentes automáticamente y extraiga conocimiento con fuente, fecha y nivel de confianza.
*   **Single Source of Truth:** La verdad reside en la base de datos normalizada, no en hojas de cálculo estáticas u opiniones.
*   **Trazabilidad y Defensa del Dato:** Todo dato debe poder responder de dónde salió (URL exacta), cuándo y qué fragmento exacto de texto lo prueba.
*   **Gestión de la Incertidumbre:** Diferenciar entre _Verificado_, _No Encontrado_, _No Existe_ y _No Verificable_, en lugar de usar un binario "Sí/No".
*   **Generalidad de Uso:** Una arquitectura conceptual escalable que permite usar el motor central para investigar cualquier vertical (salud, hacienda, medioambiente, etc.) y cualquier territorio.

## 🏗️ Arquitectura y Principios de Diseño

El diseño de MIP se rige estrictamente por los siguientes principios:

1.  **Evidencia sobre inferencia:** Ningún dato existe sin fuente verificable.
2.  **La incertidumbre es información:** No se inventan datos ni se asumen vacíos, se exponen como tales.
3.  **Todo dato debe poder defenderse:** Trazabilidad extrema (valor, fuente, fecha, agente, texto de prueba, confianza).
4.  **Single Source of Truth:** La base de conocimiento es la verdad absoluta; tableros y excels son solo proyecciones temporales.
5.  **Reproducible, auditable, verificable:** Las investigaciones pueden ser re-ejecutadas arrojando los mismos resultados o justificando sus cambios.
6.  **Modular y escalable:** Estructura fija y separada de componentes lógicos (ej. prompts, esquemas, reglas de negocio).
7.  **Independencia Tecnológica:** El conocimiento y el motor pertenecen a la plataforma. Los LLM (Claude, Gemini, etc.) son componentes intercambiables.
8.  **Generalidad primero:** MIP Core solo sabe investigar. Casos de uso específicos se montan en capas superiores de dominio.
9.  **No ocultar vacíos con promedios:** Nunca se promedia para tapar la falta de evidencia empírica.

## 📁 Estructura del Proyecto

*   `/architecture`: Diseño de la arquitectura y diagramas del motor de descubrimiento y extracción.
*   `/data`: Almacenamiento de bases de conocimiento y datasets transaccionales temporales.
*   `/decisions`: Registro de decisiones de arquitectura (ADRs).
*   `/docs`: Documentación técnica extendida del sistema.
*   `/prompts`: Prompts versionados para las diferentes llamadas e interacciones con LLMs.
*   `/schemas`: Esquemas de validación (JSON Schemas) utilizados para estructurar y asegurar las respuestas.
*   `/src`: Código fuente del núcleo organizado por sub-dominios lógicos (`discovery`, `extraction`, `impacto`, `tablero`, etc.).
*   `/tests`: Pruebas de integración y testing unitario.

## 🛠️ Tecnologías Principales

*   Lenguaje: **Python**
*   IA Generativa & Modelos: Gemnini 3.1 Pro & 3.5 flash - Google AI Studio // Claude Code // DeepSeek // Meta AI
*   Extracción y Scraping: **Requests, BeautifulSoup**, frameworks de rendering.
*   Manipulación de Datos: **Pandas**
