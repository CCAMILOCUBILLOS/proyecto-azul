# Estado del proyecto

Última actualización: 2026-10-04

## Fases

| Fase | Estado |
|---|---|
| 0. Descubrimiento | ✅ Completada |
| 1. Entorno de despliegue | ✅ Completada (ADR 0001–0003) |
| 2. Modelo de IA y voz | ✅ Completada (ADR 0004–0006, 0014) |
| 3. Estructura interna | ✅ Completada (ADR 0007–0013) |
| 4. MVP y hoja de ruta | ✅ Completada (ADR 0015–0017) |
| 5. Esqueleto del repositorio | ✅ Completada (ADR 0018–0019) |
| 6. Incremento 1: cerebro + memoria + gasto | ✅ Prueba real superada el 2026-10-05 (pendiente de aprobación del cierre) |
| 6. Incrementos 2–4 (voz, celular, respaldo) | ⏳ Pendientes |

## Incremento 1: lo que ya funciona
- Chat de texto en la app web, con respuesta por partes y botón Parar.
- Cerebro Claude Opus 5.5 con búsqueda web y esfuerzo variable por mensaje.
- Memoria en SQLite: historial y datos del usuario (herramienta `remember`).
- Control de gasto: costo por respuesta, aviso a los 40 USD y bloqueo a los 50.
- 43 pruebas automáticas.

## Prueba real (2026-10-05)
7 mensajes con datos temporales aparte; costo total: 0,161 USD.

| Mensaje | Empieza a responder | Costo |
|---|---|---|
| Saludo (caché vacía) | 7,4 s | 3,5 ¢ |
| Guardar un dato (caché vencida) | 9,4 s | 0,7 ¢ |
| Clima con búsqueda web | 15,0 s | 6,1 ¢ |
| Preguntas cortas (caché activa) | 2,0–2,7 s | 0,6 ¢ |
| Guardar un dato (caché activa) | 5,7 s | 0,8 ¢ |
| Pregunta tras aprender un dato (la caché se rehace) | 3,0 s | 3,8 ¢ |

## Próximos pasos
- Cerrar el incremento 1 y pasar al incremento 2 (voz con Deepgram).
- Mitigaciones de demora para la voz: precalentar la caché al abrir el micrófono, avisar en voz durante las búsquedas y guardar datos sin una segunda vuelta.
