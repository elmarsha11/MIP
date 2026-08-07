Acta de Cierre - Fase 2: Investigación y Limpieza de Base

Versión: 1.0 - Congelada
Fecha: 2026-08-07
Estado: CERRADA
Blueprint: docs/PROJECT_BLUEPRINT.md v1.0
ADR activo: ADR-0009 - No ocultar vacíos con promedios
Resumen Ejecutivo

Fase 2 cerrada. Resolvimos la confusión entre las dos bases y dejamos una verdad oficial.

Decisión arquitectónica clave (vos la tomaste):

    Gold Standard = Estado_de_Municipios (a mano, 86 municipios, verificado por persona). Es lo que hace hoy un investigador y lo que MIP debe automatizar. Lento pero confiable.
    Alcance / Wishlist = UdS - Relevamiento (con IA, 86 municipios, draft). Es lo que UDS quiere medir (Portal, GDE, RAFAM, etc), pero sin trazabilidad. Queda en cuarentena en research/ hasta que MIP lo verifique.

Esto nos permite no automatizar la mediocridad. No vamos a automatizar un Excel con valores inventados. Vamos a automatizar el trabajo artesanal que ya sabes que funciona.
Hallazgos Cerrados
1. Municipios: 86, no 88

Antes: Informe decía 88 con 2 perdidos MUN-BA-041 y 052.
Ahora: Validado. Eran 2 duplicados en base anterior. Los eliminaste. Quedan 86 únicos, 0 duplicados, rango MUN-BA-001 a 088 con gap intencional en 041 y 052.
Acción: Gap documentado como intencional. Dashboard corregido a 86. Total población: 2.101.764 (manual) / 2.299.900 (IA draft). Usamos 2.101.764 como oficial hasta recalcular.
2. Calidad Gold Standard (manual)

    Estado Digital: 67/86 vacíos (77,9%). No es error, es trabajo pendiente real. ADR-0009: se deja vacío.
    App Municipal: 68/86 vacíos (79,1%). Solo 4 "Si" confirmados (Mi Navarro, etc).
    Salud - Turnos online: 11/86 (12,8%) con turnos online. Este es el dolor real y la oportunidad para UDS.
    Transparencia: Texto libre, sin checklist estandarizado. Ahora definido en diccionario.

3. Calidad Alcance (IA draft)

    Matriz IA: 86 filas con 7 variables, pero 28 formas distintas de decir "Activo". No estandarizado. Sin URLs ni fragmentos.
    Dashboard IA: Dice 88 municipios y $32.743M, pero Matriz tiene 86 y hoja "5 Años" tiene solo 32 filas con $12.329M. Inconsistente.
    Acción: Todo este archivo pasa a research/alcance_uds_draft/ con estado Estimación no auditada. No se usa para cálculo hasta validación. Cumple ADR-0009.

4. Constante $31.001

Pendiente. No se encontró en ninguno de los dos Excels subidos el modelo financiero que la sustenta. Queda en cuarentena en research/ hasta que subas el Excel de métricas de impacto. Mientras tanto, todo número de impacto se muestra como Estimación no auditada.
Entregables Fase 2 Congelados

    docs/PROJECT_BLUEPRINT.md v1.0 - Constitución (ya entregado)
    decisions/0009-no-ocultar-vacios-con-promedios.md - Guardián de calidad (ya entregado)
    schemas/diccionario_datos_oficial_v1.md - Contrato operativo de qué cuenta como evidencia (nuevo)
    Fase2_Base_Trazable_v0.xlsx - Gold Standard con columnas de confianza y estado (nuevo)
    Este acta docs/Fase2_Cierre.md

Qué significa que Fase 2 esté cerrada

Podemos decir con certeza y frente a un auditor:

    Tenemos 86 municipios únicos, validados, sin duplicados.
    Sabemos que 77,9% de Estado Digital está sin relevar y no lo ocultamos con promedios.
    Sabemos que solo 12,8% tiene turnos de salud online.
    Tenemos un diccionario cerrado que define qué evidencia exige MIP para cada variable.
    Tenemos separado qué es verdad verificada (a mano) y qué es draft por verificar (IA).

Próximo paso: Fase 3 - Descubrimiento

Objetivo Fase 3: Construir el motor que hace automáticamente lo que hoy hace la persona a mano: para cada municipio, encontrar las 20 URLs donde puede estar la verdad.

Entregable Fase 3:
Para los 86 municipios, inventario de 15-25 URLs candidatas tipificadas:

    Sitio oficial
    /transparencia / SIBOM
    /turnos / salud
    Facebook oficial (muchas veces ES el canal oficial)
    Play Store / App Store
    etc.

Criterio de cierre Fase 3: investigar("Navarro") devuelve 20 URLs en <2 minutos sin intervención humana.

Qué necesito de vos para Fase 3: Nada. Ya tengo todo. Solo tu OK para arrancar.

¿Arrancamos Fase 3?

FIN Acta Fase 2