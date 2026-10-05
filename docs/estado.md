# Estado del proyecto

Última actualización: 2026-10-05

## Fases

| Fase | Estado |
|---|---|
| 0. Descubrimiento | ✅ Completada |
| 1. Entorno de despliegue | ✅ Completada (ADR 0001–0003) |
| 2. Modelo de IA y voz | ✅ Completada (ADR 0004–0006, 0014) |
| 3. Estructura interna | ✅ Completada (ADR 0007–0013) |
| 4. MVP y hoja de ruta | ✅ Completada (ADR 0015–0017) |
| 5. Esqueleto del repositorio | ✅ Completada (ADR 0018–0019) |
| 6. Incremento 1: cerebro + memoria + gasto | ✅ Completado el 2026-10-05 |
| 6. Incremento 2: voz | 🔄 Construido y probado con simulaciones; falta la clave de Deepgram, elegir la voz y la prueba real |
| 6. Incrementos 3–4 (celular, respaldo) | ⏳ Pendientes |

## Incremento 1: lo que funciona
- Chat de texto en la app web, con respuesta por partes y botón Parar.
- Cerebro Claude Opus 5.5 con búsqueda web y esfuerzo variable por mensaje.
- Memoria en SQLite: historial y datos del usuario (herramienta `remember`).
- Control de gasto: costo por respuesta, aviso a los 40 USD y bloqueo a los 50.

### Prueba real (2026-10-05)
7 mensajes con datos temporales aparte; costo total: 0,161 USD.

| Mensaje | Empieza a responder | Costo |
|---|---|---|
| Saludo (caché vacía) | 7,4 s | 3,5 ¢ |
| Guardar un dato (caché vencida) | 9,4 s | 0,7 ¢ |
| Clima con búsqueda web | 15,0 s | 6,1 ¢ |
| Preguntas cortas (caché activa) | 2,0–2,7 s | 0,6 ¢ |
| Guardar un dato (caché activa) | 5,7 s | 0,8 ¢ |
| Pregunta tras aprender un dato (la caché se rehace) | 3,0 s | 3,8 ¢ |

## Incremento 2: lo que ya está construido (ADR 0020)
- Botón de micrófono (mantener para hablar) con transcripción en vivo.
- Respuesta hablada frase por frase con Deepgram (Aura-2).
- "Déjame buscarlo" al empezar una búsqueda web.
- Precalentamiento de la caché mientras el usuario habla o escribe.
- Interrupción con el micrófono o con Parar; orden de parada por voz.
- 82 pruebas automáticas.

## Próximos pasos
- El usuario crea la cuenta de Deepgram y pega `DEEPGRAM_API_KEY` en `.env`.
- Generar muestras de las voces en español para que el usuario elija (`AZUL_TTS_VOICE`).
- Prueba real: voz sintética → Deepgram (oído) → Azul → voz, y luego la prueba del usuario con su micrófono.
- Pendiente de optimización: la ventana del historial (40 mensajes) se corre en cada turno y rehace la caché de los mensajes; conviene moverla por bloques.
