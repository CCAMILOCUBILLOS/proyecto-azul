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
| 6. Incremento 2: voz | ✅ Completado el 2026-10-05 (probado por el usuario con su voz) |
| 6. Incremento 3: celular | ✅ Completado el 2026-10-05 (probado por el usuario en su iPhone; ADR 0021) |
| 6. Incremento 4: respaldo y validación final | ⏳ Pendiente |

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

## Incremento 2: lo que funciona (ADR 0011 modificada, 0020)
- Micrófono de un solo botón: tocar para hablar; Azul detecta solo el final (1–1,5 s de silencio); el mismo botón lo calla.
- Transcripción en vivo con Deepgram Nova-3 ("Azul" como palabra clave).
- Respuesta hablada frase por frase con la voz **Gloria** (Aura-2, colombiana).
- "Dame un segundo" si tarda más de 2,5 s; "Déjame buscarlo" al buscar en internet.
- Precalentamiento de la caché mientras el usuario habla o escribe.
- Orden de parada por voz ("para", "detente"…) sin consultar al cerebro.
- 88 pruebas automáticas.

### Pruebas reales (2026-10-05)
| Caso | Resultado |
|---|---|
| Pregunta simple, fin detectado solo | Deja de escuchar a +1,5 s; texto a +3,5 s; voz a +6,1 s |
| Pregunta con dato nuevo + búsqueda web | "Dame un segundo" a ~4–5 s; "Déjame buscarlo" a ~10 s; respuesta a ~15–25 s |
| "Azul, para" | Se detiene en 0,2 s, sin costo de IA |
| Prueba del usuario con su voz | Funciona bien |

## Incremento 3: lo que funciona (ADR 0021)
- Azul en `https://dell.tailc78da3.ts.net`, solo dentro de la red de Tailscale.
- Clave de acceso una vez por dispositivo; el portátil no la pide.
- App instalable en la pantalla de inicio del iPhone, con su ícono.
- 95 pruebas automáticas.

## Próximos pasos
- Incremento 4: respaldo y restauración de la memoria; validación final de los 6 criterios del MVP.
- El usuario debe evitar que el portátil se suspenda mientras está enchufado (configuración de energía de Windows; lo hace el usuario).
- Mejoras de velocidad **aprobadas por el usuario el 2026-10-05**, para después del incremento 3:
  - A. Guardar datos sin una segunda vuelta al cerebro (~5 s menos al aprender algo).
  - B. Clima con un servicio gratuito, Open-Meteo, sin cuenta (~10 s menos en preguntas del clima).
- Descartada por ahora: bajar el silencio de fin a 0,8 s. Pendiente de evaluar: voz por streaming de Deepgram.
- Optimización de costo: la ventana del historial (40 mensajes) se corre en cada turno y rehace la caché de los mensajes; conviene moverla por bloques.
