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
| 6. Incremento 4: respaldo y validación final | ✅ Respaldo completado (ADR 0022); validación del MVP más abajo |

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

## Incremento 4: lo que funciona (ADR 0022)
- Respaldo manual (`Respaldar Azul.cmd`) y automático diario, en `respaldos/` y en `OneDrive\Azul\respaldos`; se conservan 14.
- Restauración segura (`Restaurar Azul.cmd`) con copia previa de la memoria actual.
- 105 pruebas automáticas.

## Validación del MVP v0.1 (ADR 0016)

| # | Criterio | Estado |
|---|---|---|
| 1 | Desde iPhone y Android, incluso fuera de casa, hablarle y que responda por voz | ✅ iPhone, en Wi-Fi y con datos móviles (probado por el usuario). ⏳ Android: falta instalar Tailscale |
| 2 | Empieza a responder en ~2–3 s | ⚠️ Parcial: texto 2–3 s; voz ~6 s desde que el usuario se calla; con búsqueda, 15–25 s con frases de espera |
| 3 | Recuerda entre conversaciones de días distintos | ✅ La memoria persiste entre reinicios. ⏳ Confirmar mañana ("¿cómo me llamo?") |
| 4 | "Azul, para" corta la respuesta de inmediato | ✅ 0,2 s, sin costo de IA; también el botón ■ |
| 5 | Ver el gasto del mes y que el límite funcione | ✅ Visible en la app; aviso a 40 y bloqueo a 50 USD (cubierto por pruebas) |
| 6 | Un respaldo restaurado conserva la memoria intacta | ✅ Verificado el 2026-10-05 con el respaldo de OneDrive |

**MVP v0.1.0 marcado el 2026-10-05** con aprobación del usuario (etiqueta git `v0.1.0`).

## Mejoras de velocidad (después del MVP)
- ✅ A. Memoria con notas, sin segunda vuelta (ADR 0023).
- ✅ B. Clima con Open-Meteo: 6,3 s en vez de 15–25 s (ADR 0024).
- 118 pruebas automáticas.

## v0.2.0: manos libres en el celular (completada el 2026-10-05)
- **"Oye Azul"** (ADR 0025): interruptor en la app; detector de voz local + Deepgram; ignora lo que no empieza llamando a Azul ("Oye/Hoy/Hey Azul", "Azul,"); indicador de nivel; reconexión automática. Picovoice quedó descartado: exige correo de empresa.
- **Modo conversación** (ADR 0026): un toque y Azul vuelve a escuchar tras cada respuesta, hasta una despedida ("adiós", "eso es todo"…), ■ o 8 s de silencio. Es lo que el usuario prefiere usar.
- **Atajo de Siri** (ADR 0026): `POST /api/preguntar` con la cabecera `X-Azul-Clave`. Funciona, pero Siri intercepta algunas frases ("recuerda…").
- **Honestidad** (ADR 0027): Azul guarda qué consultó de verdad (`⟦consultado: …⟧`) y no inventa datos ni fuentes; se limpió el historial con falsas confesiones.
- Arreglo: el registro técnico va a `datos/azul.log`. Un clic en la ventana negra congelaba a Azul.
- 160 pruebas automáticas. Probado por el usuario: la conversación fluye y ya no duda de lo que busca.

## v0.3: Azul en el portátil (pendiente de cerrar)
- **Cliente de escritorio** (ADR 0028): arranca con `Iniciar Azul.cmd`; escucha por el micrófono del portátil y responde por sus parlantes, sin abrir la app.
- **Ctrl + Alt + A** a cualquier hora: tono, pregunta y modo conversación. Probado por el usuario: funciona.
- **"Oye Azul"** de 07:00 a 22:00. El fin de la frase lo decide Deepgram (no el ruido del cuarto); el ruido sin palabras se corta a los 3 s y el detector aprende su nivel. ⏳ Confirmar el 2026-10-06 tras corregir el tono.
- Velocidad: esfuerzo bajo por defecto, precalentamiento y "Déjame buscarlo" al buscar.
- 188 pruebas automáticas.

## Cara visual (en curso, ADR 0029)
- Orbe neuronal en azul, morado y negro que escucha, piensa, busca y habla; la luz sigue el volumen de la voz de Azul.
- Subtítulos de la frase actual; historial y teclado detrás de botones.
- ⏳ Pendiente: prueba del usuario en el iPhone y en el PC.

## Costo del cerebro (ADR 0030)
- Lo cotidiano lo responde Claude Sonnet 5.5; "piénsalo a fondo", Claude Opus 5.5.
- La ventana del historial se mueve de a 20 mensajes para aprovechar la caché.
- Prueba real: respuesta corta a 0,21 ¢ (antes ~2,4 ¢ en promedio con Opus) y primer texto en 1,4 s.

## Red Nacional (ADR 0031, en curso)
- Herramientas listas y probadas: consultar el tablero y lanzar sus procesos por voz, con autonomía total.
- ⏳ Falta: instalar Tailscale en el PC de Optometría, publicar el tablero (`tailscale serve --bg 8765`) y poner su dirección en `AZUL_RED_NACIONAL_URL`.

## Habilidades y documentos (ADR 0032)
- Sistema de habilidades (`habilidades/<nombre>/SKILL.md`) y primera habilidad: **redacción**.
- Azul busca, lee (Word, PDF, texto), convierte PDF a Word con Word y crea documentos Word en OneDrive/Azul/Documentos, sin borrar ni sobrescribir nunca.
- Siguen: activación sin Siri (toque atrás), "Oye Azul" local en el portátil, Excel/PowerPoint, consulta jurídica, diseño de interfaces, programación y app Android.

## Toque atrás en el iPhone (ADR 0033)
- Dos toques en la parte de atrás del iPhone abren Azul (`?conversar`); un toque en la pantalla y ya escucha. Sin Siri.

## Habilidades (ADR 0032 y 0034)
- Seis habilidades: redacción, jurídica, lectura, Excel, diseño de interfaces y programación.
- Archivos: buscar, leer (Word, PDF, Excel, texto, código), PDF → Word, crear Word y Excel, y guardar páginas o código; todo en OneDrive/Azul/Documentos, sin borrar ni sobrescribir.

## Próximos pasos
- Cerrar la v0.3: confirmar "Oye Azul" en el portátil; commit, subida a GitHub y etiqueta `v0.3.0` con aprobación del usuario.
- La siguiente capacidad la elige el usuario (ADR 0017): productividad con Google y Microsoft, más control del PC, conocimiento (documentos), casa inteligente (en pausa).
- Mejora técnica pendiente: Deepgram tarda 3–5 s en dar por terminada la frase; se puede acortar.

### Dejados en pausa por el usuario (2026-10-05)
- Cambiar `AZUL_ACCESS_KEY` (quedó visible en una captura) y actualizarla en la app y en el atajo.
- Evitar que el portátil se suspenda enchufado (configuración de energía de Windows).
- Instalar Tailscale en el Android (criterio 1 del MVP).

### Otros pendientes
- Confirmar la memoria al día siguiente ("¿cómo me llamo?").
- Descartada por ahora: bajar el silencio de fin a 0,8 s. Pendiente de evaluar: voz por streaming de Deepgram.
