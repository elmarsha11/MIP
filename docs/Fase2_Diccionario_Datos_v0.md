Fase 2 - Diccionario de Datos v0 - Estado de Municipios

Fuente: Estado_de_Municipios_-_Proyecto_Regional_de_Transformación_Digital_de_la_Gestión_Municipal.xlsx
Fecha auditoría: 2026-08-07
Total registros: 86 municipios
Población total: 2.101.764 habitantes
Adhesión FRICDe: 53 True (61,6%) / 33 False
Hallazgos críticos (ADR-0009)

    Estado Digital vacío 77,9%: 67 de 86 municipios sin valor. No se puede calcular madurez.
    App Municipal vacío 79,1%: 68 de 86 sin valor. Solo 4 con "Si" confirmado.
    Salud - Solo 12,8% con turnos online: 11 de 86 tienen evidencia textual de turnos online.
    No hay IDs MUN-BA: Este archivo usa nombre directo, no IDs. Resuelve hallazgo previo de MUN-BA-041/052 pero introduce nuevo problema: no hay trazabilidad por ID único.
    Definiciones ambiguas: "Avanzado", "Básico", "Intermedio", "Desconocido" no tienen criterio operativo. ¿Qué hace que 9 de Julio sea Avanzado?

Definición operativa propuesta para Fase 2 (hasta automatizar)
Estado Digital (a estandarizar en Fase 3)

    Avanzado: Portal con >10 trámites digitales + pagos online + transparencia (presupuesto + boletín) + turnos salud online. Requiere fragmento de cada uno.
    Intermedio: Portal con 5-10 trámites + al menos 1 de: pagos, transparencia o turnos.
    Básico: Portal con 1-4 trámites, sin pagos ni turnos.
    Desconocido: Se buscó en 20 URLs y no se pudo determinar (No Verificable).
    Vacío (NaN): No investigado aún. NO es Desconocido. ADR-0009 prohíbe asignar promedio.

App Municipal

    Si: Existe en Play Store/App Store con link verificable.
    No: No existe evidencia tras búsqueda en stores + web oficial.
    Quizás: Mención en redes pero sin link a store. Pasa a No Verificable.
    Vacío: No investigado. ADR-0009.

Salud - Turnos

    Con turnos online: Texto contiene "Turnos Online", "Turnos Web", "Portal de Pacientes" + URL. Estado: Verificado con confianza Media (falta fragmento literal y URL exacta).
    Sin turnos: Texto contiene "No tiene turnos online" / "Turnos presenciales". Estado: Verificado.
    Vacío / ⎯: No Verificable.

Trámites digitales, Educación, Medioambiente, Seguridad, Transparencia

Actualmente son campos de texto libre descriptivo, no categóricos. No se puede calcular madurez numérica sin normalizar. Propuesta Fase 3: convertir cada uno en lista de hallazgos con fragmento.
Regla ADR-0009 aplicada

En esta Base Trazable v0, ningún vacío fue rellenado con promedio de sección electoral ni con constante. Todo vacío queda como "No Verificable - Vacío (ADR-0009: no rellenar con promedio)" con confianza 0%.
El cálculo de madurez y de impacto $32.743M queda en estado "Estimación no auditada - pendiente validación" hasta completar trazabilidad.
Próximos pasos Fase 2 (lo que vos tenés que validar)

    ¿Estás de acuerdo con las definiciones de Avanzado/Básico/Intermedio propuestas?
    ¿Querés que mantengamos 86 o volvemos a 88? ¿Cuáles 2 faltan?
    ¿Subimos el Modelo Financiero para auditar la constante $31.001?
