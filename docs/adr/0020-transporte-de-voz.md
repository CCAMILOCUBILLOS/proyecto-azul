# 0020. Cómo viaja la voz entre la app y el núcleo

- Estado: Aprobada (decisión de tipo B tomada por Claude Code dentro del marco aprobado)
- Fecha: 2026-10-05
- Capa: 3 (estructura interna)
- Tipo: B (reversible)

## Contexto
El incremento 2 agrega la voz (ADR 0004, 0006, 0011). La app debe funcionar igual en Android, iPhone y PC, y la prueba real del incremento 1 mostró esperas de 7 a 15 segundos en algunos casos (S11).

## Decisión
- **Captura:** la app toma el audio del micrófono con un `AudioWorklet` y lo envía como **PCM de 16 bits, mono, 16 kHz**. Safari en iPhone no graba en WebM/Opus, así que el audio sin comprimir es lo único que funciona igual en todos los navegadores (~32 KB/s, poco para la red privada).
- **Conexión:** un **WebSocket** (`/api/voz`). La app envía `hablar_inicio`, el audio en binario y `hablar_fin`; `parar` interrumpe. El núcleo responde con eventos JSON (`turno`, `escuchado`, `texto`, `buscando`, `parado`, `fin`…) y el **MP3 de cada frase** en binario.
- **Frase por frase:** la respuesta se divide en frases a medida que llega y cada una se convierte en voz apenas está completa.
- **Marca de turno:** cada respuesta empieza con `turno`, y la app descarta el audio que llegue de un turno interrumpido.
- **Deepgram directo:** se usan su WebSocket y su API HTTP sin el SDK oficial (que cambia con frecuencia de versión), con `websockets` y `httpx2`, que ya estaban en el proyecto.
- **Mitigaciones de demora:**
  - **Precalentar la caché** del cerebro (`max_tokens: 0`) mientras el usuario habla, o al empezar a escribir. Solo se hace si pasaron más de 4 minutos desde la última llamada.
  - **Decir "Déjame buscarlo"** en cuanto empieza una búsqueda web.
- **Interrupción:** tocar el micrófono o el botón Parar corta la voz y la respuesta. Una frase corta de parada ("para", "detente", "alto"…) se reconoce antes de llegar al cerebro.
- **Memoria:** se mantiene la herramienta `remember`. El usuario lo eligió el 2026-10-05, frente a extraer los datos en segundo plano (+3 a 13 USD al mes).

## Consecuencias
- El micrófono del navegador exige HTTPS fuera de `localhost`; el acceso desde el celular depende del incremento 3 (Tailscale).
- En iPhone, el audio debe activarse con un gesto del usuario; tocar el micrófono cuenta como ese gesto.
- El precalentamiento cuesta una escritura de caché (~2–3 centavos) cuando la caché venció; si no, no se hace.

## Cómo revertirla
Cada pieza está detrás de su puerto (`SpeechToText`, `TextToSpeech`) o en un módulo propio de la app (`voz.ts`).
