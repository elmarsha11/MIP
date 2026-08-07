PROJECT BLUEPRINT - Municipal Intelligence Platform (MIP)

Versión: 1.0 - Congelada
Fecha: 2026-08-07
Autor: Juli Marshall + Equipo Arquitectura (Meta AI / Claude / Gemini)
Estado: CERRADO - Fase 1 completada
Ubicación: docs/PROJECT_BLUEPRINT.md - Single Source of Truth de arquitectura

    Cualquier cambio a partir de ahora requiere un ADR en /decisions.

ÍNDICE

    Visión
    Problema
    Objetivo
    Principios
    Arquitectura Conceptual
    Modelo Mental
    Criterios de Calidad
    Roadmap General
    Definiciones
    Filosofía

1. VISIÓN

MIP no es un sistema de scraping. Es una plataforma de inteligencia territorial.

Su visión es mapear, con evidencia verificable, la capacidad real de gestión digital y administrativa de cada municipio del interior bonaerense para potenciar el desarrollo local, no para vender software.

No es un Excel más rápido. Es la memoria viva del territorio que hoy no existe. Una base que le permita a un intendente de 20.000 habitantes tener la misma calidad de información para decidir que tiene una capital, y a FRICDe tener datos duros para gestionar compras conjuntas, financiamiento CAF/BID y políticas públicas.

Si funciona, MIP se convierte en el sistema operativo de conocimiento para la gestión municipal.
2. PROBLEMA

Hoy el conocimiento sobre los municipios está fragmentado, es manual y no escala.

Cómo trabajamos hoy:

    Relevamiento manual de 88 municipios del interior PBA (luego 86 en base).
    7 variables (Portal, Turnos, GDE, etc) cargadas a mano visitando webs.
    Información dispersa en Matriz Excel, PDFs de presupuestos, SIBOM, Facebook que muchas veces ES el canal oficial, y memoria del equipo.
    Cálculo de madurez y de impacto ($32.743M) con fórmulas no trazables.

Qué encontramos en la auditoría (Informe):

    2 municipios perdidos entre Matriz (88) y base de cálculo (86): MUN-BA-041 y MUN-BA-052.
    54 de 86 municipios (62,8%) sin modelo financiero propio: se usa promedio de sección electoral para tapar el vacío.
    Constante de impacto de $31.001 por hab. x brecha con R²=1,0: indica fórmula mecánica sin fuente externa que la sustente. El número total no es auditable.
    Variables ambiguas: "Implementado", "Parcial", "Activo" sin diccionario que defina qué evidencia las prueba.

Consecuencia: No podemos escalar a 135 municipios de PBA ni defender el número frente a un auditor externo. No es un problema de código. Es un problema de arquitectura de conocimiento.
3. OBJETIVO

Objetivo General: Construir una base de conocimiento viva, auditable, escalable y con trazabilidad total que multiplique x10 la capacidad de investigación territorial.

Objetivos Específicos:

    Pasar de un Excel que se llena a una Base de Conocimiento que se interroga.
    Para cada dato, poder responder en 5 segundos: ¿Qué valor? ¿De dónde salió? ¿Cuándo? ¿Qué fragmento lo prueba? ¿Con qué confianza?
    Investigar 88 municipios hoy, 135 de PBA mañana y cualquier municipio de Argentina después, con el mismo pipeline.
    Separar claramente MIP Core (general) de Capa Dominio UDS (SAMO, DUT, GDE, Bronce/Plata/Oro).
    Que el Excel, el Dashboard y el cálculo de impacto sean proyecciones automáticas de la Base, no fuentes.

No es objetivo: Reemplazar al investigador. Automatizar la mediocridad actual. Vender un software cerrado.
4. PRINCIPIOS (Innegociables)

P1 - Evidencia sobre opinión: Si no hay fragmento de texto que lo pruebe, no hay dato.

P2 - La incertidumbre es información: No usamos binario Sí/No. Usamos 4 estados: Verificado, No Encontrado, No Existe, No Verificable. Un vacío declarado vale más que un dato inventado.

P3 - Trazabilidad total: Todo dato lleva mochila: fuente exacta, fecha de captura, fragmento, agente y confianza. Si no es trazable, no existe.

P4 - Single Source of Truth: Hay una sola base donde vive la verdad. Excel, Dashboard, API son vistas. Si cambias el Excel, se pierde. Si cambias la Base, todo se recalcula.

P5 - Generalidad primero, UDS después: Diseñamos MIP para que sirva para investigar cualquier municipio. UDS es el primer caso de uso, no el sistema.

P6 - Modularidad radical: Cada etapa hace una sola cosa y la hace bien. Podemos cambiar el LLM sin tocar el crawler.

P7 - Independencia de proveedor: No nos casamos con OpenAI, Anthropic, ni Google. El conocimiento queda en nuestra base, no en el modelo.

P8 - Separación Core vs Dominio: MIP Core sabe qué es una Fuente, un Hallazgo, un Dato y una Confianza. No sabe qué es SAMO. La capa Dominio UDS sabe qué es SAMO, DUT y Bronce/Plata/Oro y usa al Core.

P9 - No ocultar vacíos con promedios: Prohibido rellenar con promedios de sección o constantes mágicas. Ver ADR-0009.

Si violamos un principio, paramos y escribimos un ADR.
5. ARQUITECTURA CONCEPTUAL

Sin hablar de Python. Solo cómo piensa el sistema. Es un investigador que trabaja en 7 etapas en orden:

MUNICIPIO (ej: Navarro)
    ↓
[1] FUENTES → ¿Dónde puede estar la verdad?
    ↓
[2] DESCUBRIMIENTO → Encontrar todas las URLs candidatas
    ↓
[3] RECOLECCIÓN → Traer contenido crudo (texto limpio)
    ↓
[4] EXTRACCIÓN → Responder preguntas con evidencia
    ↓
[5] VALIDACIÓN → Cruzar, detectar contradicciones, asignar confianza
    ↓
[6] BASE DE CONOCIMIENTO → Guardar con identidad y trazabilidad
    ↓
[7] VISUALIZACIÓN → Proyectar (Excel, Dashboard, API)

[1] FUENTES: 10 tipos donde puede estar la verdad: sitio oficial, transparencia/SIBOM, portal de trámites, boletín/ordenanzas PDF, turnos, Facebook (canal oficial en interior), Instagram, YouTube, tiendas de Apps, medios locales.

[2] DESCUBRIMIENTO: Para cada municipio no hacemos 1 búsqueda, hacemos 20. "Navarro sitio oficial", "Navarro turnos", "Navarro hospital CAPS", "Navarro app", "Navarro Facebook oficial". Objetivo: inventario completo de URLs candidatas. Si no encontramos, guardamos No Encontrado.

[3] RECOLECCIÓN: Visitamos cada URL, entramos a /salud, /transparencia, /turnos. Si es dinámica, navegador automatizado. Si es PDF, extraemos texto. Si es Facebook, extraemos posts con keywords. Guardamos texto limpio + URL + fecha.

[4] EXTRACCIÓN: IA con bozal. Esquema JSON estricto idéntico para 88 municipios. Para cada variable debe devolver: valor + fragmento literal + URL + confianza. Sin fragmento, no hay dato.

[5] VALIDACIÓN: Cruzamos fuentes. Web dice 12 CAPS, Facebook dice 13 → guardamos las dos, marcamos contradicción, confianza Baja, tarea manual. Nunca promediamos.

[6] BASE DE CONOCIMIENTO: Todo validado con IDs únicos (MUN-BA-004). Acá vive la separación Core vs Dominio.

[7] VISUALIZACIÓN: Excel, Dashboard por sección, API, cálculo de madurez. Todo es proyección de la Base.

Capas transversales: Trazabilidad, Confianza, Orquestación.
6. MODELO MENTAL

Cómo debe pensar cualquier IA que trabaje acá.

    El sistema no busca páginas. Busca evidencia.
    No busca respuestas. Busca hechos verificables.
    No busca llenar un Excel. Busca construir conocimiento que pueda defenderse solo.

1. Piensa como investigador territorial, no como scraper. Un scraper pregunta cómo extraer. Un investigador pregunta dónde publicaría un intendente que inauguró un CAPS si no tiene web. Muchas veces en Facebook. Y si es ahí, es fuente oficial.

2. La verdad está escondida. Está en la página 14 de un PDF de presupuesto, en una ordenanza en SIBOM, en la descripción de una App en Play Store, no solo en la home.

3. La ausencia de evidencia no es evidencia de ausencia. No encontrar turnos no es No Existe. Es No Encontrado hasta tener prueba de que no existe.

4. Si hay dos verdades contradictorias, guarda las dos. No elijas. Marca contradicción y baja confianza.

5. No busques la respuesta que querés. No entres queriendo probar que tiene GDE. Entrá preguntando qué evidencia hay. Si dice "tickets" no es GDE.

6. No llenas una celda. Dejas un rastro auditable. ¿Puedo mostrar URL, fecha, fragmento y confianza en 5 segundos?

7. Piensa en general, valida en particular. ¿Esta pregunta serviría para Córdoba o Colombia? Si sí, va al Core.
7. CRITERIOS DE CALIDAD

Un dato no es bueno porque parece correcto. Es bueno cuando otro puede auditarlo.

Para entrar a la Base, todo dato debe tener 5 sellos. Si falta uno, va a cuarentena.

    Fuente Obligatoria y Accesible: URL exacta, no dominio. Ej: facebook.com/MunicipioNavarro/posts/123 no "lo vi en Facebook".
    Fecha de Captura: Cuándo lo encontramos.
    Fragmento de Evidencia Literal: Cita textual exacta que prueba el dato.
    Tipo de Fuente: Oficial Primaria, Oficial Secundaria, Terciaria.
    Nivel de Confianza (por reglas):
        Alta (90-100%): Oficial Primaria + fragmento explícito + sin contradicción.
        Media (60-89%): Oficial Primaria indirecta o Terciaria fiable.
        Baja (20-59%): Contradicción o Terciaria sola. Va a revisión humana.
        No Verificable (0%): No encontrado o contradicción total. Se guarda como vacío informado.

Regla de Oro: Solo entran automático los de Confianza Alta. Media entra marcado. Baja queda en research/ en cuarentena.

A nivel Municipio (para decir que está completo):

    Cobertura 7/7 variables con Verificado o No Encontrado.
    Frescura <30 días.
    0 contradicciones abiertas.

A nivel Lote:

    Reproducibilidad: 2 ejecuciones de Suipacha dan mismo inventario.
    Trazabilidad 100%.

8. ROADMAP GENERAL

No tareas. Solo etapas. No avanzamos hasta cerrar la anterior.

FASE 1 - ARQUITECTURA (HOY - CERRADA):
Objetivo: Cerrar Constitución. Entregable: Este archivo v1.0 + estructura carpetas + template ADR + schema base. Criterio: cualquier IA puede explicar MIP sin preguntarnos.

FASE 2 - INVESTIGACIÓN Y LIMPIEZA DE BASE:
Objetivo: Blanquear lo que ya tenemos. Entregable: Auditoría Excel, Diccionario de Datos oficial, resolución MUN-BA-041/052, 54 sin modelo propio documentados, constante $31k en cuarentena. Base SQLite v0 trazable. Criterio: cada celda del Excel actual tiene fuente o está marcada como No Verificable. $32.743M pasa a "Estimación no auditada".

FASE 3 - DESCUBRIMIENTO:
Objetivo: Motor que encuentra dónde buscar. Entregable: Para 88 municipios, 15-25 URLs candidatas tipificadas. Criterio: 10+ URLs por municipio.

FASE 4 - RECOLECCIÓN (Crawler):
Objetivo: Texto limpio, no HTML. Entregable: Corpus con texto + fecha + fuente. PDFs y Facebook. Criterio: re-ejecutable y reproducible.

FASE 5 - EXTRACCIÓN Y VALIDACIÓN (IA con bozal):
Objetivo: IA responde formulario fijo con evidencia. Entregable: LLM con JSON estricto + validador de contradicciones. Criterio: investigar("Suipacha") en <10 min con 5 sellos y 5/7 variables en Alta.

FASE 6 - VISUALIZACIÓN Y PRODUCTO:
Objetivo: Que la verdad se vea. Entregable: Base como SST, Dashboard con vacíos en rojo, API, Excel como vista, cálculo de madurez trazable. Criterio: intendente entiende su % sin llamarnos.

FASE 7 - OPERACIÓN Y ESCALADO (Futuro):
Objetivo: Plataforma viva. Entregable: Re-ejecución semanal automática, alertas de cambios, escalado a 135 y luego país. Criterio: MIP se actualiza solo.

Cada fase cierra con Revisión de Arquitectura.
9. DEFINICIONES

Para que ningún modelo interprete distinto.

Fuente: Origen público y accesible donde puede estar la verdad. Atributos: id_fuente, url_exacta, tipo, municipio_id, fecha_descubrimiento. No es un dominio suelto.

Hallazgo: Unidad mínima recolectada. Resultado crudo de visitar una Fuente. Atributos: id_hallazgo, id_fuente, texto_limpio, fragmento, fecha_captura. No es una conclusión.

Dato: Hallazgo interpretado, validado y normalizado que responde a una pregunta del esquema oficial. Solo existe si tiene trazabilidad completa. Atributos: id_dato, municipio_id, variable, valor, lista_hallazgos, confianza, estado, fecha_validacion. Tiene App = Sí en Excel sin URL no es un Dato.

Evidencia / Fragmento: Cita textual exacta (1-3 oraciones) que prueba el Dato. Si no hay fragmento, no hay Dato. P1.

Confianza: Score 0-100% que mide solidez de evidencia, no seguridad del modelo. Por reglas.

Estado de Verificación (solo 4 valores):

    Verificado: evidencia suficiente y consistente. Pasa a Base.
    No Encontrado: busqué en 20 URLs y no encontré. Vacío informado.
    No Existe: evidencia explícita de que no existe.
    No Verificable: contradicción o evidencia insuficiente. Cuarentena. Prohibido promediar.

Base de Conocimiento (Single Source of Truth): Única base normalizada con Datos con 5 sellos. Todo lo demás es proyección. Si no está en la Base, no existe.

Investigación: Proceso completo de 6 etapas para un municipio. Reproducible.

Trazabilidad: Capacidad de responder en 5 segundos: ¿Qué? ¿De dónde? ¿Cuándo? ¿Quién? ¿Qué fragmento? ¿Con qué confianza?

Términos de Dominio (UDS): SAMO, DUT, RAFAM, GDE, Bronce/Plata/Oro, Madurez, Brecha son de capa Dominio UDS. Se definen en schemas/dominio_uds.json. Core no necesita saberlos. P8.
10. FILOSOFÍA

MIP no existe para vender software. Existe para devolverle inteligencia al territorio.

Los municipios de 20.000 habitantes sostienen hospitales, arreglan caminos rurales y contienen a familias con una ley de 1958 y un Excel. Mientras, las capitales tienen observatorios. Esa asimetría es una injusticia territorial. MIP nace para cerrarla.

Nuestras creencias:

1. No reemplazamos al investigador. Multiplicamos su capacidad x10. La IA hace el trabajo arqueológico de 10 plataformas para que el humano haga lo que solo el humano puede: entender contexto y decidir con criterio.

2. No automatizamos la mediocridad. Construimos conocimiento. Automatizar el Excel con 2 municipios perdidos y 54 promediados sería más rápido pero seguiría siendo mediocre. Preferimos un dashboard rojo con vacíos honestos que uno verde con promedios inventados. Un vacío honesto vale más que un promedio bonito de $32.743M.

3. El conocimiento pertenece al territorio, no al modelo. Si mañana cambiamos de LLM, el conocimiento no se pierde. Si UDS deja de existir, la base de 135 municipios sigue. Diseñamos para 10 años, no 10 sprints.

4. La transparencia no es un feature. Es herramienta de desarrollo. Un dato trazable deja de ser un número y se convierte en argumento para un crédito BID o una compra conjunta en FRICDe. La trazabilidad es poder para el que gestiona.

5. Preferimos un sistema humilde que dice "no sé" a uno soberbio que inventa. Decir "no encontré evidencia de GDE" es información útil. Es una tarea pendiente. Es más útil que poner "Parcial" por vergüenza a dejar una celda vacía.

MIP es nuestra forma de decir que un municipio chico merece la misma calidad de inteligencia que una capital. No buscamos páginas. Construimos la memoria del territorio.