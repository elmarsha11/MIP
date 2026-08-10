# Validación: DeepSeek vs Gemini en Fase 4 (2026-08-09)

**Veredicto: DeepSeek NO reemplaza a Gemini todavía.** Encuentra menos evidencia y
produce falsos positivos que la verificación de ADR-0014 no puede frenar.

La capa agnóstica (`src/llm/`) queda igual: sirve y es la que permitió medir esto.
Lo que no se hace es cambiar el proveedor por defecto.

---

## Cómo se midió

Se corrió `procesar()` con cada proveedor sobre el mismo municipio, con las mismas
páginas y el mismo prompt, sin cache y sin escribir en la base. Se comparó variable
por variable.

Se eligieron municipios por volumen de texto: Chascomús es el caso degenerado (393
caracteres, portal JS), los otros tres tienen entre 25.000 y 29.000 caracteres.

## Resultados

| Municipio | Chars | Gemini verif. | DeepSeek verif. | Contradicciones |
|---|---:|---:|---:|---:|
| Chascomús | 393 | 5/20 | 3/20 | 0 |
| Ayacucho | 25.150 | **12/20** | 7/20 | 0 |
| General Villegas | 28.717 | **7/20** | 5/20 | 0 |

**Cobertura:** DeepSeek pierde entre 2 y 5 variables por municipio. En Ayacucho
encuentra 7 donde Gemini encuentra 12: **42% menos evidencia**.

**Coherencia:** cero contradicciones. Donde los dos verifican, coinciden en el
valor. DeepSeek no dice cosas distintas — dice menos cosas.

**Costo:** 1 llamada por municipio en ambos. El gasto no cambia.

---

## El problema real: falsos positivos que la verificación no frena

Más grave que la cobertura. Dos casos, los dos con **cita literal válida** que pasó
la verificación de ADR-0014 y que aun así no prueba nada.

### 1. General Villegas — `turnos_salud_online = si`

> Cita: *"Para turnos, comunicarse al 3388 672564 de 8 a 14 horas."*

El diccionario dice textualmente que *"solo un telefono fijo es 'no'"*. Un teléfono
no es un turnero digital. Peor: en la misma respuesta DeepSeek puso
`canal_turnos_salud = telefono`, **contradiciéndose a sí mismo**.

Gemini respondió `no_verificable`, que es correcto.

Esta es la variable de mayor valor comercial. Un falso positivo acá mete a General
Villegas en el grupo equivocado y le saca un prospecto a UDS.

### 2. Ayacucho — `expediente_digital_gde = si`

> Cita: *"Convenio con Vientos de Libertad para fortalecer la atención y
> acompañamiento de personas con consumos problemáticos"*

La cita existe literal en la página. No tiene ninguna relación con expediente
digital.

### Por qué la verificación no los atrapa

El guard de *"el valor tiene que estar dentro de la cita"* (trampa ya documentada en
el handoff §7) solo aplica a variables de texto libre. En variables binarias el
valor es `si`/`no`, que nunca va a estar literal en la cita. Ahí queda el agujero.

Es la misma lección del handoff §9.4, ahora con evidencia nueva:
**ADR-0014 frena la alucinación, no el error de criterio.**

---

## Dos bugs reales encontrados y corregidos

La comparación sirvió para encontrar dos errores en `deepseek_provider.py` que no
se veían sin correrlo contra datos de verdad:

1. **`response_format` con `schema` no existe en DeepSeek.** Su modo JSON es solo
   `{"type": "json_object"}`: garantiza JSON sintácticamente válido, no su forma.
   Gemini sí fuerza el esquema. Ahora el esquema se inyecta como mensaje de sistema.
2. **DeepSeek exige la palabra "json" en los mensajes** cuando se pide ese modo. El
   prompt de Fase 4 no la tiene (habla de citas y variables). La aporta el sistema.
3. **`temperature` estaba en 0.7.** Fase 4 audita, no redacta: se bajó a 0.0. Una
   cita parafraseada la tumba la verificación.

Los tres arreglos viven en el provider, no en `extractor.py`. Fase 4 no sabe con
qué modelo habla, y esa es la idea.

---

## Qué queda pendiente si se quiere insistir con DeepSeek

En orden de probabilidad de servir:

1. **Partir el pedido.** Hoy se piden las 20 variables en una sola llamada sobre
   28.000 caracteres. Es mucha tarea junta. Pedir de a 5 variables cuadruplica las
   llamadas, pero con DeepSeek eso cuesta centavos. Es la hipótesis más prometible
   para cerrar la brecha de cobertura.
2. **Cerrar el agujero de las binarias.** Pedirle al modelo que además marque qué
   parte de la cita justifica un `si`, y verificar eso. Sirve para los dos
   proveedores, no solo para DeepSeek.
3. **`deepseek-reasoner`** en vez de `deepseek-chat`. Más lento y más caro, pero la
   tarea es de razonamiento sobre texto largo.

## Qué NO hacer

No cambiar `MIP_LLM_PROVIDER` a `deepseek` por defecto, y no correr los 86 con
DeepSeek para "ver qué pasa": ADR-0013 protege lo verificado de ser pisado por un
vacío, pero **no protege de un falso positivo**, que sí pisa. Una corrida completa
con DeepSeek hoy le mete a la base datos peores que los que tiene.

---

## Cómo reproducir

El script está en el scratchpad de la sesión, no versionado. Compara sin escribir
en la base:

```bash
python comparar_proveedores.py Ayacucho
```
