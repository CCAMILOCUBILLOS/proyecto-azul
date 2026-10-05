# 0004. La voz funciona en cadena

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 2 (modelo de IA)
- Tipo: A (difícil de revertir)

## Contexto
La prioridad del usuario es la máxima inteligencia, y además exige poder migrar (R1). El portátil no puede correr modelos locales.

## Opciones consideradas
1. En cadena: voz → texto → cerebro → texto → voz.
2. Voz a voz: un único modelo en tiempo real (Gemini Live, OpenAI Realtime).

## Decisión
Opción 1.

## Consecuencias
- Permite usar el modelo más inteligente, sin importar la voz.
- Cada pieza (oído, cerebro, voz) se cambia por separado.
- Queda registro en texto, lo que sirve para la memoria y la migración.
- Implica ~1 a 2 segundos de pausa, que se reducen empezando a hablar antes de terminar la respuesta.

## Cómo revertirla
Pasar a voz a voz implicaría reemplazar el flujo de conversación y aceptar un modelo menos capaz.
