# 0014. Selección de modelo: un modelo con esfuerzo variable

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 2 (modelo de IA)
- Tipo: B (reversible)

## Contexto
El usuario preguntó si Azul podía usar modelos más baratos para preguntas simples (por ejemplo, el clima). Costo estimado por turno, con la memoria en caché:

| Modelo | Por turno | Al mes (~1.800 turnos) |
|---|---|---|
| Opus 5.5 | ~0,8 ¢ | ~14 USD |
| Sonnet 5.5 | ~0,4 ¢ | ~8 USD |
| Haiku 4.5 | ~0,2 ¢ | ~4 USD |

## Opciones consideradas
1. Un solo modelo (Opus 5.5) con esfuerzo variable.
2. Un enrutador automático: Haiku para lo simple y Opus para lo complejo.
3. Un modelo medio (Sonnet 5.5) que consulta a Opus como asesor.

## Decisión
Opción 1 en el MVP. La pieza de enrutamiento queda **preparada en el diseño**. Tras 2 o 3 semanas de uso real se presentarán los datos de gasto, y el enrutador se activa **solo con la aprobación del usuario**.

## Consecuencias
- Siempre inteligencia de nivel tope.
- Se pierde un ahorro posible de ~5–6 USD al mes, que se reevaluará con datos.

## Cómo revertirla
Activar el enrutador por configuración.
