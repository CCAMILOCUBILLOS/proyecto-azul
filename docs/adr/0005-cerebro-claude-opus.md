# 0005. El cerebro principal es Claude Opus 5.5

- Estado: Aprobada (modificada el 2026-10-04: antes era Claude Opus 5) (ajustada por ADR 0030: Opus queda para lo difícil)
- Fecha: 2026-10-04
- Capa: 2 (modelo de IA)
- Tipo: A (difícil de revertir), mitigado por la interfaz `Brain`

## Contexto
Máxima inteligencia con un presupuesto de 20 a 50 USD al mes. Precios por millón de tokens (entrada / salida), octubre de 2026.

## Opciones consideradas
| Modelo | Precio | Observación |
|---|---|---|
| Claude Opus 5 | $5 / $25 | Nivel tope (la primera elección) |
| Claude Opus 5.5 | $4 / $20, caché a $0,20 | Sucesor de Opus 5, más barato |
| Gemini 3.1 Pro | $2 / $12 | Nivel tope, pero en *Preview* |
| GPT-6 Astra | $10 / $50 | Puede exceder el presupuesto |
| Claude Sonnet 5 / GPT-6.1 Sol | $2 / $10 | Un escalón abajo |

Nota: la recomendación la hizo Claude (Anthropic), y se le advirtió al usuario de ese posible sesgo.

## Decisión
Claude Opus 5.5, modelo `claude-opus-5-5`, configurable en `AZUL_BRAIN_MODEL`.

## Consecuencias
- Unos 12–16 USD al mes con uso moderado (ver ADR 0014).
- Es de lanzamiento reciente; volver a Opus 5 es un cambio de configuración.
- En este modelo el razonamiento no se puede desactivar; se controla con el nivel de esfuerzo.

## Cómo revertirla
Cambiar `AZUL_BRAIN_MODEL`, o escribir otro adaptador de `Brain` para otro proveedor.
