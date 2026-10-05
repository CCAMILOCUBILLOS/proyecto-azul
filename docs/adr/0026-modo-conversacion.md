# 0026. Modo conversación y el atajo de Siri

- Estado: Aprobada (preferencia del usuario el 2026-10-05)
- Fecha: 2026-10-05
- Capa: 3
- Tipo: B (reversible)

## Contexto
El usuario quería no depender de dejar la pantalla encendida.
- Se probó un **atajo de Siri** ("Oye Siri, Azul" → dictado → `POST /api/preguntar` con la clave en la cabecera `X-Azul-Clave` → Siri muestra o lee la respuesta). Funcionó, pero Siri interpreta algunas frases como órdenes propias: "recuerda que me gusta el café…" creó un recordatorio de Siri.
- Preferencia del usuario: *"que se abra el ícono de Azul y de ahí empezar a hablar con ella hasta detenerme"*.

## Decisión
- **Modo conversación:** un toque en 🎤 inicia la conversación. Tras cada respuesta, cuando termina el audio y tras 350 ms, Azul **vuelve a escuchar sola**. Termina cuando:
  - el usuario se despide o pide parar ("para", "adiós", "chao", "eso es todo", "nada más", "hasta luego"…), lo que se reconoce sin consultar a la IA;
  - toca ■ mientras Azul responde;
  - pasan 8 s sin hablar;
  - o hay un error o se llega al límite de gasto (no se insiste en bucle).
- Tras un "Oye Azul" sin pregunta, también se entra en modo conversación.
- La ruta `POST /api/preguntar` y la clave en la cabecera se mantienen: el atajo de Siri sigue siendo una opción para preguntas rápidas.
- En iPhone sigue haciendo falta **un toque** para empezar, porque Apple exige un gesto para activar el audio. Se puede abrir la app con "Oye Siri, abre Azul".

## Consecuencias
- La conversación fluye sin tocar la pantalla tras el primer toque.
- El micrófono se pausa mientras Azul habla, para no escucharse a sí misma.
- Cada turno usa Deepgram mientras escucha; se cobran como cualquier turno de voz.

## Cómo revertirla
En `app/src/main.ts`, quitar la llamada a `continuarConversacion()`; el micrófono vuelve a ser de un turno por toque.
