# 0035. "Oye Azul" reconocido en el portátil, sin internet (Vosk)

- Estado: Aprobada (librería, modelo y horario de 24 horas aprobados por el usuario el 2026-10-06)
- Fecha: 2026-10-06
- Capa: 3 (cómo escucha el cliente de escritorio) y 4 (librería y modelo de Vosk)
- Tipo: B (reversible): borrar el modelo de `datos/modelos/` y Azul vuelve a usar Deepgram

## Contexto
Con el ADR 0028, cada fragmento con voz se enviaba a Deepgram para saber si decía "Oye Azul": costaba un poco por cada ruido con voz, y por eso había horario (07:00–22:00). El usuario quiere a Azul atenta siempre sin gastar.

## Opciones consideradas
1. **Vosk** (Apache 2.0) con su modelo pequeño de español (39 MB): reconocimiento local.
2. openWakeWord: exige entrenar un modelo propio para "Oye Azul" (datos sintéticos y GPU).
3. Picovoice: descartado antes (exige correo de empresa).

## Decisión
Vosk con el **vocabulario completo** (con un vocabulario reducido a "oye azul" confundía casi cualquier frase con el llamado). El detector de voz por volumen sigue decidiendo cuándo hay alguien hablando; solo entonces el audio pasa por Vosk, así que en silencio casi no gasta procesador (30 s de silencio: 1,3 s de cómputo). Se acepta "azul" entre las tres primeras palabras con solo palabras de llamado antes ("oye azul", "azul, …", y las confusiones típicas del modelo: "hoy azul", "voy azul", "oye soul"…). Se revisan las tres lecturas más probables al cerrar cada frase.

Al reconocerlo: tono, turno nuevo con el audio de esa frase (hasta 6 s, para no perder la pregunta dicha de corrido) y, desde ahí, Deepgram como siempre. El núcleo quita el llamado del texto ("Oye Azul, ¿qué hora es?" → "¿qué hora es?") y, si solo se dijo "Oye Azul", sigue escuchando la pregunta.

Horario: todo el día (`AZUL_ESCRITORIO_DESDE` = `AZUL_ESCRITORIO_HASTA` significa siempre).

## Consecuencias
- Esperar cuesta cero: lo que se dice sin llamar a Azul nunca sale del portátil.
- Prueba con voces sintéticas (2026-10-06): 13 de 16 llamados reconocidos y 0 falsas alarmas en 20 frases ajenas. Falta la prueba con la voz real del usuario; si falla, Ctrl+Alt+A sigue funcionando.
- Memoria: ~100–200 MB más mientras corre el cliente; carga del modelo, ~1 s.
- Si falta el modelo o la librería, el cliente vuelve al método del ADR 0028 (Deepgram).

## Cómo revertirla
Borrar `datos/modelos/vosk-model-small-es-0.42` (vuelve a Deepgram) o `AZUL_ESCRITORIO_OYE_AZUL=false`.
