Diccionario de Datos Oficial v1 - Gold Standard

Versión: 1.0 - Congelado
Fecha: 2026-08-07
Fuente Gold Standard: Estado_de_Municipios_-_Proyecto_Regional_de_Transformación_Digital_de_la_Gestión_Municipal.xlsx (86 municipios, verificado a mano)
Fuente Alcance: UdS_-_Relevamiento_de_Modernización_y_Gestión_Digital_de_Municipios_PBA.xlsx (86 municipios, draft IA - en cuarentena)
Autor: Arquitectura MIP + Juli Marshall
Relacionado: ADR-0009, PROJECT_BLUEPRINT.md Cap. 7 y 9

    Este es el contrato que debe cumplir MIP. Si la IA no puede probar un dato con estos criterios, el dato no entra. Va a cuarentena.

1. Campos Base (identidad)
Municipio

    Definición: Nombre oficial del municipio.
    Tipo: String único.
    Regla: 86 valores únicos, sin duplicados. Validado 2026-08-07. Gold Standard.
    IDs faltantes: MUN-BA-041 y 052 eliminados por ser duplicados en base anterior. Gap intencional.

Cant. Habitantes

    Definición: Población estimada.
    Tipo: Integer.
    Fuente Gold: Censo / estimación municipal.
    Trazabilidad requerida para MIP: Fuente + año. Si no, confianza Media.

Adhesión FRICDe

    Definición: ¿Municipio adherido a FRICDe?
    Tipo: Boolean (True/False)
    Evidencia requerida: Acta / listado oficial FRICDe. En Gold Standard manual se da por Verificado.

2. Variables Core - Lo que MIP debe automatizar

Todas estas variables deben cumplir los 5 sellos del Cap. 7: URL exacta, fecha, fragmento literal, tipo de fuente, confianza.
A) Estado Digital (Columna crítica)

Situación actual Gold Standard: 67/86 vacíos (77,9%). No es error, es que aún no fue relevado o no hay evidencia clara. ADR-0009: se deja vacío, no se promedia.

Definición operativa para MIP v1:

    Avanzado: Portal oficial con >15 trámites en línea visibles + botón de pago online funcional + sección de transparencia con presupuesto + boletín/SIBOM + turnos de salud online. Evidencia: 4 URLs distintas, una por cada criterio.
        Ej Gold: 9 de Julio

    Intermedio: Portal con 5-14 trámites + al menos 2 de: pago online, transparencia completa, turnos online.
        Ej Gold: Balcarce, Chacabuco

    Básico: Portal con 1-4 trámites o solo informativa. Sin pago online ni turnos. Es el mínimo digital.
        Ej Gold: Adolfo Alsina, Arrecifes, Ayacucho

    Desconocido: Se ejecutó pipeline de descubrimiento (20 búsquedas) y no se pudo determinar estado por falta de evidencia o contradicción. Estado = No Verificable, confianza Baja, va a revisión humana.

    Vacío (NaN): No investigado aún por MIP. Estado = No Verificable, confianza 0%, no se usa para cálculo de madurez. ADR-0009.

Regla MIP: Estado Digital no se infiere. Se calcula a partir de las otras 6 variables. Si Trámites, Salud y Transparencia están vacíos, Estado Digital = Vacío.
B) Trámites digitales

Gold Standard actual: Texto libre con lista de trámites (ej: "Bromatología, Licencias, Tesorería...").

Definición operativa MIP:

    Valor: Lista normalizada de trámites encontrados.
    Evidencia requerida: URL de /tramites o /guia-tramites + fragmento que liste cada trámite. Ej: .../tramites contiene "Licencias de conducir".
    Confianza Alta: Si hay URL + fragmento con nombre del trámite.
    Confianza 0% si: Texto genérico "tiene trámites" sin lista.

C) Salud

Gold Standard actual: Texto descriptivo de CAPS, hospitales + si tiene turnos online.

Definición operativa MIP - 2 sub-variables:

    Infraestructura: Cantidad de CAPS/Hospitales mencionados (extrae número si existe: "CAPS (7)").
    Turnos Online (CRÍTICA):
        Si tiene: Texto contiene "Turnos Médicos Online" / "Turnos Web" / "Portal de Pacientes" + URL funcional a turnero. Confianza Alta solo con URL.
        No tiene: Texto contiene "No tiene turnos online" / "Turnos presenciales" / "No encontré portal web ni turnos online" (ej: 9 de Julio, Brandsen). Verificado.
        Vacío: Sin mención. No Verificable.

Métrica clave para UDS: Solo 11/86 (12,8%) con turnos online en Gold Standard. Ese es el dolor real.
D) Educación / Medioambiente / Seguridad

Gold Standard actual: Texto libre descriptivo de programas.

Definición operativa MIP v1: Por ahora, campo de texto con hallazgos. No se calcula madurez numérica. Se guarda como lista de hallazgos con fuente. En v2 se normaliza a categorías.
E) App Municipal

Situación actual: 68/86 vacíos, 10 No, 4 Si, 4 Quizás.

Definición operativa MIP:

    Si: Encontrada en Google Play Store y/o App Store con búsqueda "Municipalidad de X". Evidencia: URL de store + nombre exacto de app. Confianza Alta.
        Ej: "Mi Navarro", "MH App" (Monte Hermoso), "MUNI BOT 25"
    No: Búsqueda en stores + web oficial sin resultados tras 20 búsquedas. Verificado con fecha.
    Quizás: Mención en Facebook/Instagram pero sin link a store. Estado = No Verificable, confianza Baja, tarea manual.
    Vacío: No investigado. ADR-0009.

F) Transparencia

Gold Standard actual: Lista de elementos (Presupuesto, Boletín, Licitaciones, SIBOM, etc).

Definición operativa MIP - Checklist:
MIP debe buscar y marcar presencia de cada item con URL:

    Presupuesto anual
    Boletín Oficial / SIBOM
    Licitaciones
    Recibos de sueldo / escala salarial
    Ordenanzas
    Declaraciones juradas

Confianza Alta si tiene al menos Presupuesto + Boletín + 1 más con URLs.
3. Variables Alcance (del Excel IA - en cuarentena)

Estas vienen del archivo UdS - Relevamiento... Matriz (IA draft). Son el QUÉ quiere medir UDS a futuro. Hoy están en cuarentena por ADR-0009.

    Portal y Transparencia
    Turnos Digitales
    Cobro Electrónico de Tasas
    Expediente Digital (GDE)
    Reclamos Urbanos (147/App)
    Sistema RAFAM
    Ventanilla Única

Estado actual: 28 formas distintas de decir "Activo". No estandarizado. Valores como "Activo (Transparencia)", "Medio-Alto (SIBOM)", "Parcial (tickets)" no tienen criterio operativo.

Regla: Ningún valor de este archivo entra a la Base hasta que MIP lo re-releve con los 5 sellos. Queda en research/alcance_uds_draft/ como referencia de alcance, no como verdad.

Próximo paso Fase 3: Unificar ambos diccionarios. Mapear "Turnos Digitales" (IA) con "Salud - Turnos" (Gold Standard) + "Trámites digitales".
4. Reglas de Calidad aplicadas (Cap. 7 + ADR-0009)

    Sin fragmento, no hay dato. Todo "Si" o "Implementado" debe tener URL exacta y cita textual.
    Vacío no es 0. Un NaN es No Verificable, confianza 0%. No se promedia con municipios vecinos ni con sección electoral.
    "Quizás" = tarea humana. Todo valor ambiguo va a cola de revisión, no a Dashboard.
    Trazabilidad 5 sellos: Fuente + fecha + fragmento + tipo + confianza. Si falta uno, va a cuarentena.

Este diccionario es el contrato de aceptación de Fase 3, 4 y 5. Si MIP genera un dato que no cumple esto, no pasa.

FIN v1.0 - Fase 2