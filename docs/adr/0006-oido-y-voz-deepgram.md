# 0006. Oído y voz con Deepgram

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 2 (modelo de IA)
- Tipo: B (reversible)

## Contexto
La voz en cadena (ADR 0004) necesita convertir voz a texto y texto a voz, en español.

## Opciones consideradas
1. Deepgram para ambas piezas (Nova-3 multilingüe + Aura-2): ~13–15 USD/mes.
2. Deepgram + ElevenLabs (voz más natural): ~20–22 USD/mes.
3. La voz del navegador: gratis, pero de baja calidad y poco fiable en iPhone.

## Decisión
Opción 1.

## Consecuencias
- Pendiente verificar la calidad de las voces en español antes de construir sobre ellas.
- ElevenLabs queda como mejora posible.

## Cómo revertirla
Escribir otro adaptador de `SpeechToText` o de `TextToSpeech`.
