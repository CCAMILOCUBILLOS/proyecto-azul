# 0025. "Oye Azul": detector de voz local + Deepgram

- Estado: Aprobada por el usuario el 2026-10-05 (reemplaza la elección inicial de Picovoice)
- Fecha: 2026-10-05
- Capa: 3 y 4
- Tipo: B (reversible)

## Contexto
La v0.2 agrega la activación por voz (ADR 0011), empezando por el celular con la app abierta (decisión v0.2-a del usuario).

El motor elegido primero, **Picovoice Porcupine**, resultó inviable: su consola rechaza correos personales ("introduzca un correo electrónico válido de la empresa"). Sherpa-ONNX no tiene modelos en español.

## Opciones consideradas (decisión reabierta)
1. Detector de voz local + Deepgram.
2. openWakeWord, entrenando "Oye Azul" en español con Colab.
3. El reconocimiento de voz del navegador (poco fiable en iPhone).

## Decisión
Opción 1:
- **En el celular** (`app/src/deteccion.ts`): un detector de volumen que aprende el ruido de fondo. Cuando hay voz (≥ 0,2 s sobre el ruido), envía ese fragmento a Azul, con 0,5 s previos para no cortar el "Oye"; lo cierra tras 1,2 s de silencio o 30 s de duración. **No envía nada mientras no hay voz**, ni mientras Azul piensa o habla.
- **En el núcleo** (`core/wake.py`, `VoiceSession.handle_wake`): Deepgram transcribe el fragmento.
  - Si **empieza** con "Oye Azul" (o "hey/ey/oiga Azul"), responde solo a lo que sigue.
  - Si dijeron solo "Oye Azul", la app hace un tono y abre la escucha normal.
  - Si no es para Azul, **se descarta sin mostrarlo ni guardarlo**, y no se prepara la caché ni se consulta a la IA.
- **Protocolo:** `activacion_inicio` / audio / `activacion_fin`; el núcleo responde `ignorado` o `activado`, o la respuesta normal.
- **App:** un interruptor "Oye Azul" en la cabecera, que se activa con un toque (requisito del iPhone) y pide mantener la pantalla encendida (`wakeLock`).
- Se reduce la espera al precalentamiento de 3 s a 1 s: esperarlo de más retrasaba la respuesta.

## Consecuencias
- Prueba real (voz sintética): "Pásame la sal" → ignorado en 0,2 s; "Oye Azul, ¿qué día es hoy?" → respuesta hablada correcta. Costo: 3,9 ¢.
- **Costo:** se cobran los segundos de voz cercana con la app abierta (Deepgram, ~0,29 USD por hora de voz). Estimado: 1–5 USD al mes; más con la TV o conversaciones cerca. Entra en el límite de 50 USD.
- **Privacidad:** los fragmentos con voz cercana van a Deepgram, aunque no sean para Azul; Azul no los guarda.
- iPhone: solo con la app abierta y la pantalla encendida. Gasta más batería.

## Cómo revertirla
Apagar el interruptor; o reemplazar el detector y `handle_wake` por un motor dentro del dispositivo si aparece una opción viable.
