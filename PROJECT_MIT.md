 MIP - Municipal Intelligence Platform (v0.1 - borrador)

## CAPITULO 1 - Declaración (v0.1 - borrador)
MIP es una plataforma de inteligencia territorial diseñada para descubrir, estructurar, validar y mantener actualizada la información pública de los municipios, transformando información dispersa en conocimiento verificable para apoyar la toma de decisiones.

Qué NO es MIP:
-> No es un scraper.
-> No es un ETL de Excel a Excel.
-> No es una herramienta para UDS.
-> No es un dashboard.

Esas son solo técnicas o consecuencias.

Qué SÍ es MIP:
-> Es un motor de adquisición de conocimiento. Un sistema que investiga a nivel municipal y territorial: encuentra fuentes oficiales donde estén (web oficial, redes sociales, boletín oficial, PDF de presupuesto, Google Play, etc.), extrae texto limpio, contrasta, valida y deja trazabilidad completa de cada dato.

Para quién existe:
-> MIP busca resolver el problema del interior bonaerense -los 135 municipios regulados por una ley de 1958 que hoy tienen que hacer salud, seguridad y desarrollo con herramientas analógicas-, pero su vocación es general. Está pensado para cualquier organización que necesite entender un municipio: una consultora, una universidad, un organismo multilateral como CAF, un foro de intendentes como el FRICDe o una empresa de software como UDS.

El cambio de paradigma:
-> Pasamos de "buscar en Google manualmente y anotar en un Excel" a "tener una base de conocimiento viva, reproducible, auditable y comparable entre municipios".

No reemplazamos al investigador. Multiplicamos su capacidad.

## CAPITULO 2 - Problema (v0.1 - borrador)
El problema no es que falte información sobre los municipios. El problema es que esa información es imposible de usar.

Hoy, entender un municipio del interior bonaerense exige un trabajo manual, lento y no reproducible que no escala.

El problema tiene tres capas, una sobre la otra:

> Capa 1 - Parálisis institucional (el origen):
Los 135 municipios de PBA siguen regulados por la Ley Orgánica de Municipalidades (Decreto-Ley 6769/58), diseñada para alumbrado, barrido y limpieza. En 60 años se les delegó salud primaria, seguridad preventiva, obra pública, desarrollo económico y contención social, sin una modernización correlativa. El resultado, como describe tu relevamiento funcional, se repite en las 11 secretarías:

-> Fragmentación en silos secretariales. No hay expedientes digitales unificados (GDE), hay papel.
-> Desfase tecnológico. No hay inventario georreferenciado de obras, no hay trazabilidad de medicamentos en CAPS, no hay padrón único de beneficiarios sociales.
-> Lógica recaudatoria por sobre prestación. Catastral, comercial y contribuyentes no dialogan, aunque todos usen RAFAM.

Un intendente de 20.000 a 60.000 habitantes gobierna con sistemas analógicos y dependiendo de personas clave, no de procesos. Es lo que viste en FRICDe: no pueden resolver caminos rurales destruidos, arsénico en agua o basurales colapsados, no por falta de plata, sino por incapacidad para formular, planificar y probar.

> Capa 2 - Fragmentación informacional (el síntoma que nos toca a nosotros):
Esa parálisis institucional produce una información que es:

-> Dispersa: No hay una API. La verdad de un municipio está repartida entre su web oficial (si existe), Facebook (que en muchos casos ES el canal oficial), Instagram, SIBOM, boletines en PDF, presupuestos escaneados, Google Play/App Store, WhatsApp y notas de medios locales.
-> Sin estándar: "Turnos Digitales" para tu relevamiento puede ser un formulario web en Suipacha, un Bot de WhatsApp en Exaltación de la Cruz, una App Mi Navarro o una fila a las 5 AM. Son incomparables.
-> Volátil y engañosa: Una app figura como "Implementada" pero no funciona hace dos años. Un portal de transparencia existe pero no publica licitaciones. Un municipio dice tener 12 CAPS y en Facebook inaugura el 13. La verificación es manual.
-> No trazable: Tu propio relevamiento de 88 municipios lo demuestra: 86 identificados individualmente, 2 perdidos (MUN-BA-041 y 052, 62.000 hab de diferencia), 54 de 86 sin modelo financiero propio apoyados en promedios de sección. Y variables como GDE, 147/App o Habilitación Express existen en menos del 15-30% de los casos relevados.

> Capa 3 - Ceguera para decidir (la consecuencia):
Sin información comparable y verificable:

-> No se puede planificar inversión pública de calidad (como advierte CAF en RED 2025).
-> No se puede demostrar solvencia para acceder a crédito BID/CAF ni armar compras conjuntas entre municipios (el objetivo de FRICDe).
-> No se puede vender tecnología B2G con un argumento de "se paga solo" si no podemos probar con evidencia dura dónde se pierde el recupero SAMO o la recaudación por DUT.
-> Por eso terminamos en fórmulas mecánicas como Población x Brecha x $31.001 con R²=1,0. No es un error, es la consecuencia de no tener evidencia dura. Es un placeholder por falta de datos reales.

En una frase:
El investigador hoy no investiga. Hace arqueología manual en 10 plataformas distintas para intentar responder preguntas simples como "¿tiene turnero?" y cuando cree tener la respuesta, no puede probar de dónde la sacó.

Ese es el enemigo que MIP viene a destruir.

## CAPITULO 3 - Objetivos (v0.1 - borrador)
Objetivo General:
Construir una plataforma capaz de investigar automáticamente municipios bonaerenses, recopilar evidencia pública, estructurarla y generar una base de conocimiento confiable, comparable, verificable y actualizable que transforme información dispersa en conocimiento para la toma de decisiones.

Esa frase que escribiste en el pipeline no se toca. Es el objetivo madre.

Objetivos Específicos - Qué significa eso en la práctica:

1. Reemplazar el trabajo manual por un motor investigador:
Pasar del relevamiento manual de 88 municipios (86 identificados, con 7 variables cualitativas) a un agente que, dado un municipio, descubra automáticamente sus fuentes oficiales (web, transparencia, turnos, Facebook, SIBOM, boletín en PDF, app en stores), extraiga texto limpio, y responda siempre las mismas preguntas con la misma estructura JSON, con fuente, fecha y confianza.

2. Instalar el Single Source of Truth:
Que el Excel deje de ser la verdad. La verdad pasa a ser una base de datos normalizada. De ahí sale todo: API, Dashboard, Excel, informes para CAF/BID, y el cálculo de madurez. Nunca al revés. Si un dato no está en la base con su evidencia, no existe.

3. Hacer que todo dato pueda defenderse:
Cualquier dato del sistema debe poder responder: ¿Qué valor tiene? ¿De dónde salió (URL exacta)? ¿Cuándo se encontró? ¿Qué agente lo encontró? ¿Qué fragmento de texto lo prueba? ¿Qué confianza tiene? Queremos poder responder "¿Por qué Chascomús tiene 93%?" sin abrir 10 pestañas.

4. Convertir la incertidumbre en información:
Dejar de usar "Sí/No" binario. El sistema debe distinguir y registrar:

-> Verificado (hay evidencia)
-> No Encontrado (busqué en X fuentes y no apareció)
-> No Existe (hay evidencia de que no existe)
-> No Verificable (hay contradicción entre fuentes)
-> Esto es lo que hoy nos falta y nos obliga a usar fórmulas mecánicas como $31.001 por habitante.

5. Construir una plataforma general con un primer caso de uso concreto:
MIP Core no sabe qué es SAMO, DUT o RAFAM. Solo sabe investigar. La capa de dominio UDS (los 5 ejes: Gestión Financiera/Recaudación, Salud SAMO/HCU, Producción DUT, Expediente Digital GDE, Atención Vecinal 147/App + las 11 secretarías) vive arriba. El primer hito de éxito de MIP es lograr que el relevamiento de los 88 municipios que hoy es manual, incompleto (faltan MUN-BA-041/052 y 54 sin modelo propio) y estático, pase a ser automático, completo, trazable y actualizable semanalmente.

Qué NO es objetivo de MIP en esta fase (para no desviarnos):

-> No es desarrollar el SaaS Bronce/Plata/Oro para municipios. Eso lo hace UDS Gestión Digital después, usando MIP como inteligencia.
-> No es reemplazar al investigador. Es multiplicar su capacidad x10.
-> No es hacer el scraper perfecto. El scraping es una técnica, no el objetivo.
-> No es hacer consultoría. No vamos a decirle a un intendente qué hacer, vamos a darle evidencia para que decida.

Definición de Éxito - ¿Cuándo decimos que el Objetivo 3 está cumplido?
Cuando podamos ejecutar investigar("Navarro") y en menos de 10 minutos tener para las 7 variables de la Matriz (Portal, Turnos, Cobro, GDE, Reclamos, RAFAM, Ventanilla) un objeto con valor, fuente, fecha, fragmento y confianza >80%, reproducible por cualquiera que corra el sistema, y comparable con Suipacha o Chascomús.

## CAPÍTULO 4: PRINCIPIOS (v0.1 - borrador)

Este capítulo no se discute en cada sprint. Se obedece. Si una decisión técnica choca con un principio, se cambia la decisión técnica, no el principio.

| P1 - Evidencia sobre inferencia. Ningún dato existe sin fuente.
Regla: No guardamos "Tiene App = Sí". Guardamos "Tiene App = Sí | Fuente: https://navarro.gob.ar/... | Fragmento: 'Descargá Mi Navarro' | Fecha: 2026-08-07 | Confianza: 96%".
Por qué: Es lo que nos diferencia de un ETL. Sin fuente, es opinión. Con fuente, es conocimiento.
Violación: Poner un valor en la base porque "parece que sí" o porque "ChatGPT lo dijo".

| P2 - La incertidumbre es información, no un bug.
Regla: Nunca usamos Sí/No binario. Usamos cuatro estados obligatorios: Verificado, No Encontrado (busqué en X lugares y no está), No Existe (hay evidencia de que no existe), No Verificable (fuentes se contradicen).
Por qué: Esto destruye la necesidad de inventar. Hoy tuvimos que poner "No" cuando en realidad era "No Encontrado", y por eso terminamos promediando 54 municipios sin datos propios.
Violación: Usar "No" o "Promedio de sección" para tapar un vacío.

| P3 - Todo dato debe poder defenderse.
Regla: Cualquier dato debe poder responder en 5 segundos: ¿Qué valor? ¿De dónde salió? ¿Cuándo? ¿Quién lo encontró (qué agente)? ¿Qué texto lo prueba? ¿Qué confianza tiene?
Por qué: Es la base para que un intendente, CAF o el Tribunal de Cuentas crea en el dato. Si no podemos responder "¿Por qué Chascomús tiene 93%?", no sirve.
Violación: Un dato en la base sin URL, sin fecha y sin fragmento.

| P4 - Single Source of Truth. La base es la verdad, el Excel es una vista.
Regla: La verdad vive en un solo lugar: la base de conocimiento normalizada. Todo lo demás (Excel, Dashboard, informe para UDS, API) es una proyección de esa base. Nunca al revés.
Por qué: Hoy la verdad está en 3 tablas distintas que no coinciden (86 en matriz, 32 con modelo propio, 7 secciones agregadas). Por eso se pierden 2 municipios.
Violación: Editar el Excel manualmente y no volcarlo a la base. Tener dos "versiones finales".

| P5 - Reproducible, auditable, verificable.
Regla: Cualquier investigación debe poder re-ejecutarse por otra persona, con otro modelo, y llegar al mismo resultado o entender por qué cambió (la fuente cambió).
Por qué: Si no es reproducible, no es ciencia territorial, es artesanía.
Violación: Un script que solo corre en tu máquina y guarda resultados sin log.

| P6 - Modular y escalable. Diseñamos para 10 personas, aunque hoy seamos 4.
Regla: Cada decisión de arquitectura debe favorecer que mañana seamos más, no menos. Estructura de carpetas fija, prompts versionados en /prompts, esquemas en /schemas, decisiones en /decisions (ADRs). Un módulo no rompe a otro.
Por qué: Es lo que prometiste: "No voy a dejar que se convierta en una maraña de scripts".
Violación: Poner lógica de negocio dentro de un prompt. Crear una carpeta utils_final_v2.

| P7 - Independencia tecnológica. El conocimiento es de la plataforma, no del modelo.
Regla: Debemos poder cambiar de proveedor de IA (Claude, Gemini, yo) o de crawler (Playwright, Trafilatura) sin reescribir la plataforma. El LLM es un componente intercambiable, no el cerebro.
Por qué: Si atamos MIP a un modelo, MIP muere cuando el modelo cambia de precio o de API.
Violación: Guardar lógica crítica dentro de un prompt propietario que solo funciona en un modelo.

| P8 - Generalidad primero. UDS es el primer caso de uso, no el producto.
Regla: MIP Core no sabe qué es SAMO, DUT o RAFAM. Sabe investigar. La ontología de UDS (11 secretarías, 5 ejes funcionales, paquetes Bronce/Plata/Oro) vive en una capa de dominio por encima.
Por qué: Esto nos permite venderle mañana MIP a una universidad que quiere investigar ambiente o a un banco que quiere evaluar riesgo fiscal municipal, sin reescribir nada.
Violación: Hardcodear "Paquete Oro" dentro del motor de descubrimiento de fuentes.

| P9 - No ocultamos vacíos con promedios. Un dato faltante vale más que un dato inventado.
Regla: Si 54 municipios no tienen modelo financiero propio, lo declaramos como No Verificable - Falta modelo propio y lo mostramos en el dashboard. No lo tapamos con el promedio de la sección. Nunca.
Por qué: Este principio nace directamente del hallazgo R²=1,0 del informe. Un número inventado pero bonito ($32.743M) destruye la confianza frente a un organismo multilateral. Un vacío declarado genera una tarea de investigación.
Violación: Cualquier fórmula Población x Brecha x Constante sin fuente externa que la sustente.

## CAPÍTULO 5: ARQUITECTURA CONCEPTUAL (v0.1 - borrador)

MIP no es un scraper gigante. Es un investigador que trabaja en 6 etapas, siempre en el mismo orden. Cada etapa tiene una sola responsabilidad.


MUNICIPIO (ej: Navarro)
 ↓
[1] FUENTES → ¿Dónde puede estar la verdad?           
 ↓                                                             
[2] DESCUBRIMIENTO → Encontrar todas las URLs candidatas    
 ↓ 
[3] RECOLECCIÓN → Traer el contenido crudo (texto limpio, no HTML)    
 ↓                                                             
[4] EXTRACCIÓN → Responder preguntas con evidencia                    
 ↓                                                             
[5] VALIDACIÓN → Cruzar, detectar contradicciones, asignar confianza  
 ↓                                                             
[6] BASE DE CONOCIMIENTO → Guardar con identidad y trazabilidad      
 ↓                                                             
[7] VISUALIZACIÓN → Proyectar (Excel, Dashboard, API)                 

1. FUENTES - El mapa del territorio:
No buscamos "la web del municipio". Buscamos 10 tipos de fuentes donde puede estar la evidencia: sitio oficial, portal de transparencia/SIBOM, portal de trámites/ventanilla única, boletín oficial/ordenanzas (PDF), sistema de turnos, Facebook (que en el interior MUCHAS veces es el canal oficial), Instagram, YouTube, tiendas de Apps (Mi Navarro, etc), y medios locales. Esta lista sale de tu Matriz y del análisis de las 11 secretarías. Cada fuente tiene un peso distinto.[1]

2. DESCUBRIMIENTO - El perro de caza:
Para cada municipio no hacemos 1 búsqueda, hacemos 20. "Navarro sitio oficial", "Navarro portal transparencia", "Navarro turnos", "Navarro hospital CAPS", "Navarro app", "Navarro Facebook oficial", etc. El objetivo no es encontrar una página, es construir el inventario completo de URLs candidatas para ese municipio. Si no encontramos la URL oficial en 20 intentos, guardamos No Encontrado y no inventamos.[2]

3. RECOLECCIÓN - El recolector limpio:
Visitamos cada URL del inventario. No solo la home. Entramos a /salud, /transparencia, /turnos, /tramites. Si es una web dinámica, usamos un navegador automatizado. Si es un PDF de presupuesto, lo descargamos y extraemos el texto. Si es Facebook, extraemos publicaciones con palabras clave (turnos, hospital, becas). Guardamos siempre el texto limpio, la URL y la fecha. Nada de HTML.[3]

4. EXTRACCIÓN - El analista con formulario fijo:
Acá entra la IA, pero con bozal. No le pedimos que "resuma". Le damos un esquema JSON estricto que es idéntico para los 88 municipios: ¿tiene portal de trámites? ¿tiene turnos online? ¿cuántos CAPS? ¿tiene app? ¿tiene GDE? Para cada respuesta debe devolver obligatoriamente: valor + fragmento de texto que lo prueba + URL + confianza. Si no hay fragmento, no hay dato. Esto es lo que hoy haces manual en la columna "Portal y Transparencia".[4]

5. VALIDACIÓN - El detector de mentiras:
Cruzamos fuentes. Si la web dice "12 CAPS" y una noticia de Facebook dice "Se inauguró el CAPS N°13", no elegimos una. Guardamos las dos como hallazgos, marcamos contradicción, bajamos confianza a Media y creamos una tarea Verificar manualmente. Acá también aplicamos el principio P9: nunca promediamos. Si 2 fuentes se contradicen, no inventamos una tercera.[5]

6. BASE DE CONOCIMIENTO - El Single Source of Truth:
Todo lo validado se guarda normalizado, con IDs únicos (MUN-BA-004, FUENTE-004-A, HALLAZGO-004-1). Acá vive la separación clave:

-> MIP Core: sabe qué es una Fuente, un Hallazgo, un Dato y una Confianza. No sabe qué es SAMO.[6]
-> Capa Dominio UDS: sabe que SAMO, DUT y GDE son importantes y que pertenecen a Salud, Producción y Gobierno. Sabe que Bronce/Plata/Oro son paquetes.
-> Usa los datos del Core para calcular madurez.

Si un dato no está acá con su trazabilidad, no existe.

7. VISUALIZACIÓN - Las ventanas:
El Excel que hoy usas, el Dashboard por sección electoral, el informe para CAF, el cálculo de $32.743M, todo es una proyección de la Base. No son fuentes. Si cambias algo en el Excel, se pierde. Si cambia algo en la Base, todo se recalcula.[7]

Capas transversales que cruzan todo:

-> Trazabilidad: cada dato lleva mochila (fuente, fecha, agente, fragmento).
-> Confianza: cada dato tiene score, no es binario.
-> Orquestación: podemos re-ejecutar solo Navarro, solo la etapa de Validación, o solo los municipios que cambiaron la semana pasada.

## CAPÍTULO 6: MODELO MENTAL (v0.1 - borrador)

Este capítulo no existe en la mayoría de los proyectos. En MIP es obligatorio. Le dice a cualquier agente, humano o artificial, cómo debe pensar cuando investiga un municipio.

Si solo te acordás de una frase, que sea esta:

-> El sistema no busca páginas. Busca evidencia.
-> No busca respuestas. Busca hechos verificables.
-> No busca llenar un Excel. Busca construir conocimiento que pueda defenderse solo.

Cómo piensa un investigador de MIP:

1. Piensa como un investigador territorial, no como un scraper.
Un scraper pregunta "¿cómo extraigo esta web?". Un investigador pregunta "¿dónde un intendente de 20.000 habitantes publicaría que inauguró un CAPS si no tiene web?". La respuesta muchas veces es: en Facebook. Y si Facebook es donde publica, Facebook ES la fuente oficial. No es menos seria.

2. La verdad está escondida, no expuesta.
Mucha de la verdad municipal no está en una home linda. Está en la página 14 de un PDF de presupuesto, en una ordenanza escaneada en SIBOM, en la descripción de una App en Google Play que dice "Descargá Mi Navarro para sacar turnos", o en un comentario de un vecino en Instagram. Si solo miras la home, vas a guardar No Encontrado cuando en realidad era Verificado.

3. La ausencia de evidencia no es evidencia de ausencia.
No encontrar turnos online después de buscar en 20 URLs no significa que no existan. Significa No Encontrado. Para decir No Existe necesitas evidencia de que no existe. Esta distinción es la que nos salva de inventar datos y nos obliga a seguir buscando. Es el corazón del Principio P2.

4. Si hay dos verdades contradictorias, no elijas. Guarda las dos.
Web oficial dice "12 CAPS". Facebook oficial dice "Inauguramos el CAPS N°13". No promedias. No eliges la más nueva. Guardas los dos hallazgos, marcas contradicción, bajas confianza a Media y creas una tarea Verificar manualmente. El sistema nunca oculta una contradicción. La expone. Es el Principio P9.

5. No busques la respuesta que querés. Busca el hecho que podés probar.
No entras a investigar Navarro queriendo probar que "tiene GDE". Entras preguntando "¿qué evidencia hay sobre GDE?" Si el fragmento dice "tickets" y no "expediente digital", no es GDE. No fuerces el dato para que cierre el modelo financiero de $31k. Un vacío declarado vale más que un dato forzado.

6. No estás llenando una celda. Estás dejando un rastro para que otro pueda auditarte.
Cada vez que guardas algo, pregúntate: ¿Si Juli o un auditor de CAF me pregunta mañana "¿por qué pusiste esto?" puedo mostrarle URL, fecha, fragmento y confianza en 5 segundos? Si la respuesta es no, no lo guardes.

7. Piensa en general, valida en particular.
Cuando diseñes una pregunta, pensá: ¿esta pregunta serviría para investigar un municipio en Córdoba o en Colombia? Si la respuesta es sí, va al Core. Si solo sirve para UDS (¿tiene SAMO?), va a la capa de Dominio. Así mantenemos MIP general y UDS como primer caso de uso.

En resumen: sé desconfiado, sé trazable y sé humilde con lo que no sabes. No reemplazas al investigador. Le das una lupa 10 veces más potente.

## CAPÍTULO 7: CRITERIOS DE CALIDAD (v0.1 - borrador)

En MIP un dato no es bueno porque "parece correcto". Es bueno cuando otro investigador puede auditarlo y llegar a la misma conclusión. La calidad no es subjetiva, es verificable.

Todo dato individual, para entrar a la Base, debe tener 5 sellos obligatorios. Si le falta uno, no entra. Va a cola de revisión.

1. Fuente Obligatoria y Accesible:
Regla: URL exacta, no dominio. No vale navarro.gob.ar. Vale https://navarro.gob.ar/transparencia/licitaciones-2026.pdf.
Ejemplo que NO pasa: "Lo vi en Facebook" sin link al post.
Ejemplo que SÍ pasa: https://www.facebook.com/MunicipioNavarro/posts/12345

2. Fecha de Captura:
Regla: Cuándo lo encontramos. No cuándo se publicó. La info municipal cambia todo el tiempo.
Por qué: Si mañana la App deja de funcionar, sabemos que el 07-08-2026 sí funcionaba.

3. Fragmento de Evidencia Literal:
Regla: El texto exacto que prueba el dato, copiado tal cual. 1 a 3 oraciones.
Ejemplo malo (hoy en tu Excel): Portal y Transparencia = Implementado
Ejemplo bueno (MIP): Valor: Implementado | Fragmento: "Descargá la App Mi Navarro para solicitar turnos de licencias" | Fuente: Google Play

4. Tipo de Fuente:

-> Oficial Primaria: web oficial, boletín oficial, SIBOM, app oficial, Facebook oficial verificado como canal del municipio.
-> Oficial Secundaria: RAFAM, Tribunal de Cuentas, Boletín Provincial.
-> Terciaria: medio local, Google Maps, comentario.
-> La confianza depende de esto. Una App en Play Store vale más que una nota de un diario local diciendo "el municipio lanzaría una app".

5. Nivel de Confianza Operativo (no es a ojo):

-> Alta (90-100%): Fuente Oficial Primaria + fragmento explícito + sin contradicción. Ej: Web oficial dice "Sistema de turnos online" y el link funciona.
-> Media (60-89%): Fuente Oficial Primaria pero indirecta, o Terciaria fiable con fragmento claro. Ej: Facebook oficial publica foto de fila con texto "ya podés sacar turno por WhatsApp" pero no hay link. O dos fuentes oficiales que coinciden parcialmente.
-> Baja (20-59%): Contradicción entre fuentes, o fuente Terciaria sola. Ej: Web dice 12 CAPS, Facebook dice 13. No se puede decidir. Va a revisión humana obligatoria.
-> No Verificable (0%): Busqué en 20 URLs y no encontré nada, o hay contradicción total. Se guarda como No Encontrado o No Verificable, no como No.

Regla de Oro de Calidad:
Solo entran automático a la Base los datos con Confianza Alta. Los de Confianza Media entran pero marcados para revisión semanal. Los de Confianza Baja no entran a la Base, quedan en cuarentena en research/.

Criterios a nivel Municipio (para medir si un municipio está "bien investigado"):

Para decir que Navarro está completo, necesitamos:

-> Cobertura: 7/7 variables de la Matriz con al menos un hallazgo Verificado o No Encontrado (no vacío).
-> Frescura: ningún dato con más de 30 días sin re-validar.
-> Sin contradicciones abiertas: 0 hallazgos en estado Baja sin resolver.

Hoy, con tu relevamiento, ningún municipio pasa este filtro. Y está bien. Ese es el punto de partida honesto. El 52,4% de madurez que calculaste no es un dato de calidad Alta, es una estimación de confianza Media/Baja porque le falta fragmento y fuente. MIP lo va a blanquear.

Criterios a nivel Lote (para medir si una ejecución del pipeline fue buena):

-> Reproducibilidad: si corro 2 veces la investigación de Suipacha hoy, ¿obtengo el mismo inventario de URLs?
-> Trazabilidad 100%: ¿el 100% de los datos en la Base tiene los 5 sellos?

Si algo no pasa estos criterios, no lo tapamos con un promedio de sección. Lo dejamos en rojo en el dashboard como tarea pendiente. Eso es calidad.

## CAPÍTULO 8: ROADMAP GENERAL (v0.1 - borrador)

No hay fechas. Hay etapas. No avanzamos de fase hasta que la anterior esté cerrada con su criterio de éxito. Cada domingo revisamos arquitectura.

### FASE 1 - ARQUITECTURA (Donde estamos hoy)
Objetivo: Cerrar la Constitución.
Entregable: PROJECT_BLUEPRINT.md v1.0 con los 10 capítulos + estructura de carpetas + template de ADRs + schema JSON base con los 5 sellos de calidad.
Criterio de cierre: Vos decís "los 10 capítulos están cerrados" y cualquier IA que lea el blueprint puede explicar qué es MIP sin preguntarnos.
No es: Código.

### FASE 2 - INVESTIGACIÓN Y LIMPIEZA DE BASE (Fundación de datos)
Objetivo: Blanquear lo que ya tenemos antes de automatizar.
Entregable: Auditoría de tu Excel actual. Diccionario de Datos oficial de las 7 variables (qué significa "Parcial", "Activo", "Semipresencial"). Resolución de los 3 hallazgos del Informe: identificar MUN-BA-041/052, documentar por qué 54 municipios no tienen modelo propio y poner en cuarentena la constante de $31.001/hab hasta tener fuente externa que la sustente. Base SQLite v0 con 86 municipios con trazabilidad manual.
Criterio de cierre: Podemos responder con fuente para cada celda del Excel actual o marcarla como No Verificable sin inventar promedios. El número de $32.743M pasa a mostrarse como "Estimación no auditada - pendiente validación constante $31k".
No es: Automatizar todavía.

### FASE 3 - DESCUBRIMIENTO
Objetivo: Que el sistema encuentre solo dónde buscar.
Entregable: Motor que, dado "Navarro", devuelve inventario de 15-25 URLs candidatas tipificadas: web oficial, transparencia, turnos, SIBOM, Facebook oficial, Instagram, YouTube, app en Play Store, etc. Con tipo de fuente.
Criterio de cierre: Para los 88 municipios tenemos al menos 10 URLs candidatas por municipio y podemos explicar por qué Facebook es fuente Oficial Primaria en algunos casos.

### FASE 4 - RECOLECCIÓN (Crawler)
Objetivo: Traer texto limpio, no HTML.
Entregable: Corpus con texto limpio de cada URL, con fecha de captura. PDFs de presupuestos/boletines descargados y con texto extraído. Posts de Facebook con palabras clave (turnos, CAPS, becas) extraídos.
Criterio de cierre: Podemos re-ejecutar la recolección de Chascomús y obtener el mismo corpus si nada cambió en las webs.

### FASE 5 - EXTRACCIÓN Y VALIDACIÓN (IA con bozal)
Objetivo: Que la IA responda el formulario fijo con evidencia.
Entregable: LLM con esquema JSON estricto para las 7 variables + 5 ejes (SAMO, DUT, GDE, etc) que devuelve valor + fragmento + URL + confianza. Módulo de validación que cruza fuentes, detecta contradicciones (12 vs 13 CAPS) y asigna confianza Alta/Media/Baja. Datos de Baja quedan en cuarentena.
Criterio de cierre: Ejecutamos investigar("Suipacha") y en <10 min tenemos 7 variables con los 5 sellos de calidad y confianza Alta para al menos 5 de ellas. Sin inventar.

### FASE 6 - VISUALIZACIÓN Y PRODUCTO
Objetivo: Que la verdad se vea y se use.
Entregable: Base como Single Source of Truth. Dashboard por sección electoral que muestra madurez real (con vacíos en rojo, no promediados), API simple, y Excel generado como vista. Cálculo de madurez y brecha 100% trazable: si dice 52,4%, puedo clickear y ver qué 6 evidencias lo componen.
Criterio de cierre: Un intendente o un analista de CAF puede entender por qué su municipio tiene X% sin llamarnos. El impacto financiero se muestra con disclaimer de confianza.

### FASE 7 - OPERACIÓN Y ESCALADO (Futuro)
Objetivo: Pasar de proyecto a plataforma viva.
Entregable: Re-ejecución automática semanal de los 88, alertas de cambios (ej: "Navarro lanzó nueva app"), escalado a 135 municipios de PBA y luego a otras provincias. MIP Core usable por terceros sin la capa UDS.
Criterio de cierre: MIP se actualiza solo y nosotros solo revisamos las contradicciones de confianza Baja.

Cada fase termina con una Revisión de Arquitectura: ¿seguimos resolviendo el problema correcto? ¿La arquitectura sigue simple? ¿Qué deuda técnica generamos?


# CAPÍTULO 9: DEFINICIONES (v0.1 - borrador)

1. Fuente
Definición: Origen público y accesible donde puede estar la verdad de un municipio.
Atributos: id_fuente, url_exacta, tipo (Oficial Primaria / Oficial Secundaria / Terciaria), municipio_id, fecha_descubrimiento.
Ejemplo: https://www.facebook.com/MunicipioDeNavarro/posts/123 es una Fuente Oficial Primaria si es el canal oficial del municipio.
Qué NO es: Un dominio suelto (navarro.gob.ar) no es una Fuente. Es un lugar donde buscar fuentes.

2. Hallazgo
Definición: Unidad mínima de información recolectada. Es el resultado crudo de visitar una Fuente. Todavía no es un Dato, es evidencia en bruto.
Atributos: id_hallazgo, id_fuente, texto_limpio, fragmento, fecha_captura, id_agente.
Ejemplo: Hallazgo-004-1: "Descargá la App Mi Navarro para solicitar turnos" extraído de Google Play el 07-08-2026.
Qué NO es: No es una conclusión. No dice "tiene app". Solo dice "encontré este texto acá".

3. Dato
Definición: Un Hallazgo interpretado, validado y normalizado que responde a una pregunta del esquema oficial. Solo existe si tiene trazabilidad completa.
Atributos: id_dato, municipio_id, variable (ej: tiene_app), valor, lista_de_hallazgos_que_lo_prueban, confianza, estado, fecha_validacion.
Ejemplo: Dato: municipio=Navarro, variable=tiene_app, valor=Sí, hallazgos=[H-004-1, H-004-2], confianza=96%, estado=Verificado
Qué NO es: Tiene App = Sí en un Excel sin URL ni fragmento no es un Dato. Es una anotación.

4. Evidencia / Fragmento
Definición: Cita textual exacta (1-3 oraciones) dentro de un Hallazgo que prueba el Dato. Es la prueba judicial.
Regla: Si no hay fragmento, no hay Dato. Punto. P1.

5. Confianza
Definición: Score 0-100% que mide qué tan sólida es la evidencia, no qué tan seguro está el modelo. Se calcula por reglas, no a ojo.
Regla: Oficial Primaria + fragmento explícito + sin contradicción = Alta (90-100%). Contradicción = Baja automática.

6. Estado de Verificación
Definición: Situación de un Dato después de la validación. Solo 4 valores permitidos, nunca binario Sí/No.

-> Verificado: Hay evidencia suficiente y consistente. Pasa a la Base.
-> No Encontrado: Busqué en 20 URLs tipificadas y no encontré evidencia. Se guarda como vacío informado, no como No.
-> No Existe: Hay evidencia explícita de que no existe. Ej: ordenanza que dice "derógase sistema de turnos online".
-> No Verificable: Hay contradicción entre fuentes o evidencia insuficiente. Va a cuarentena para revisión humana. Es el estado que hoy tapamos con promedios y que el Principio P9 prohíbe.

7. Base de Conocimiento (Single Source of Truth)
Definición: Única base de datos normalizada donde viven los Datos con sus 5 sellos (fuente, fecha, fragmento, confianza, estado). Todo lo demás (Excel, Dashboard, API, informe de impacto de $32.743M) es una proyección. Si no está en la Base, no existe.

8. Investigación
Definición: Proceso completo de 6 etapas (Descubrimiento → Recolección → Extracción → Validación → Base → Visualización) ejecutado para un municipio. Debe ser reproducible por otra persona en otro momento.

9. Trazabilidad
Definición: Capacidad de responder en 5 segundos para cualquier Dato: ¿Qué valor? ¿De dónde salió? ¿Cuándo? ¿Quién lo encontró? ¿Qué fragmento lo prueba? ¿Con qué confianza? Si no puedes responder eso, no es trazable y no entra a la Base. P3.

10. Términos de Dominio (UDS) - Fuera del Core
Definición: SAMO, DUT, RAFAM, GDE, Habilitación Express, Bronce/Plata/Oro, Madurez, Brecha, etc, son términos de la capa de Dominio UDS. No se definen acá. Se definen en schemas/dominio_uds.json. MIP Core no necesita saber qué es SAMO para funcionar. Esta separación es el Principio P8.


# CAPÍTULO 10: FILOSOFÍA (v0.1 - borrador)

MIP no existe para vender software. Existe para devolverle inteligencia al territorio.

Los municipios de 20.000 habitantes del interior bonaerense sostienen hospitales, arreglan caminos rurales que se inundan, contienen a familias sin laburo y tienen que rendir cuentas al Tribunal de Cuentas con una ley de 1958 y un Excel. Mientras tanto, las grandes ciudades tienen observatorios, dashboards y equipos de datos. Esa asimetría de inteligencia es una injusticia territorial.

MIP nace para cerrar esa brecha.

Nuestras creencias, no negociables:

1. No reemplazamos al investigador. Multiplicamos su capacidad x10.
No queremos una IA que escriba informes sola. Queremos una IA que haga el trabajo arqueológico manual de 10 plataformas para que el investigador humano pueda hacer lo que solo un humano puede hacer: entender el contexto, detectar una contradicción y tomar una decisión con criterio. Si MIP hace que una persona pueda investigar 10 municipios en el tiempo que antes investigaba 1, ganamos.

2. No automatizamos la mediocridad. Construimos conocimiento.
Automatizar el Excel que hoy tenemos, con sus 2 municipios perdidos y sus 54 promediados, sería más rápido pero seguiría siendo mediocre. No queremos hacer más rápido lo que hoy se hace mal. Queremos hacerlo bien, aunque al principio sea más lento y el dashboard esté lleno de rojos que dicen No Verificable. Un vacío honesto vale más que un promedio bonito de $32.743M. Ese es nuestro acto de honestidad frente a un intendente y frente a CAF.

3. El conocimiento pertenece al territorio, no al modelo que lo generó.
MIP no es de Claude, ni de Gemini, ni mío, ni tuyo. Es de la plataforma. Si mañana cambiamos de LLM porque salió uno mejor, el conocimiento no se pierde. Si mañana UDS deja de existir, la base de conocimiento sobre los 135 municipios sigue. Diseñamos para que esto viva 10 años, no 10 sprints.

4. La transparencia no es un feature. Es una herramienta de desarrollo.
Cuando un dato tiene fuente, fecha y fragmento, deja de ser un número para discutir y se convierte en un argumento para conseguir un crédito BID, para armar una compra conjunta en FRICDe, o para que un secretario de salud pueda reclamar presupuesto con evidencia de que el SAMO no se recupera. La trazabilidad no es burocracia. Es poder para el que gestiona.

5. Preferimos un sistema humilde que dice "no sé" a uno soberbio que inventa.
En el interior bonaerense, decir "no encontré evidencia de que tengan GDE" no es un fracaso. Es información. Es una tarea pendiente de investigación. Es mucho más útil que poner "Parcial" porque nos da vergüenza dejar una celda vacía. MIP nunca va a adivinar para quedar bien.

En definitiva, MIP es nuestra forma de decir que un municipio chico merece la misma calidad de inteligencia territorial que una capital. Y que esa inteligencia no se construye comprando herramientas sueltas que no hablan entre sí, sino construyendo una base de conocimiento viva, auditable y compartida.

No buscamos páginas. Construimos la memoria del territorio.

                                                                By - Juli Marshall

========================================================================================================================================================