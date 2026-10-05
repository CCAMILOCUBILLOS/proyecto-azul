# 0010. Un solo agente con herramientas

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 3 (estructura interna)
- Tipo: A (difícil de revertir)

## Contexto
La conversación por voz exige poca demora y un costo controlado.

## Opciones consideradas
1. Un solo agente que usa herramientas.
2. Varios agentes especialistas con un coordinador.
3. Un framework externo (por ejemplo, LangGraph).

## Decisión
Opción 1, usando directamente el SDK de Anthropic detrás del puerto `Brain`. Las herramientas se definen en un registro propio, compatible con MCP si en el futuro se aprueba.

## Consecuencias
- Simple, rápido y fácil de diagnosticar.
- Si un día hacen falta especialistas, se agregan sin rehacer el núcleo.

## Cómo revertirla
Agregar orquestación encima del mismo registro de herramientas.
