# 0036. Interrumpir a Azul con la voz, solo con la voz del usuario

- Estado: Aprobada (celular y portátil; modelo de hablantes aprobado por el usuario el 2026-10-07)
- Fecha: 2026-10-07
- Capa: 3 (cómo escucha Azul mientras responde) y 4 (modelo de hablantes de Vosk)
- Tipo: B (reversible): borrar `datos/modelos/vosk-model-spk-0.4` o "Olvidar mi voz"

## Contexto
El usuario quiere poder corregir o cortar a Azul mientras habla, sin esperar a que termine, y que eso solo funcione con su voz (no con otras personas, la TV ni el eco de la propia Azul).

## Decisión
- **Huella de voz** (x-vector de 128 números, modelo `vosk-model-spk-0.4`, local y gratis). El usuario la enseña una vez en la app: 5 frases de 5 segundos (panel de la conversación → "Enseñarle mi voz"). Se guarda solo la huella numérica en `datos/huella_voz.json`; también se calcula la huella de la voz de Azul (Gloria) para no confundirse con su eco.
- **Veredicto** en el núcleo con 2,2 s de voz: "sí" si se parece al usuario ≥ 0,48 y al menos 0,15 más que a Azul; "dudoso" entre 0,33 y 0,48, y entonces se escucha hasta 3,5 s y se decide otra vez. Se registran solo los números, para ajustar.
- **Protocolo**: mientras Azul responde, la app o el cliente envían `interrupcion_inicio` y el audio; el núcleo responde `interrumpido` (Azul se calla, la respuesta queda a medias en el historial y ese audio abre un turno nuevo) o `no_eres_tu` (sigue).
- **Celular y navegador**: el navegador cancela el eco; mientras se verifica, Azul baja su volumen al 20 %.
- **Portátil** (sin cancelación de eco): un vigía aprende cuánto de la voz de Azul vuelve al micrófono y solo sospecha si oye bastante más que eso; entonces Azul hace una pausa y se verifica con audio limpio.

## Opciones consideradas
- Interrumpir con cualquier voz (sin huella): Azul se interrumpiría con su propio eco y con otras personas.
- Cancelación de eco por software en el portátil: exige librerías nativas o numpy; queda como mejora futura.

## Consecuencias
- Calibración con voces sintéticas: con 1,2 s de voz no se distingue bien (0,41 vs 0,38); con 2 s o más sí (0,52–0,77 el mismo hablante, ~0,40 otro hombre, 0,11–0,24 Azul). Prueba de punta a punta: el "usuario" interrumpió en 3 de 4 frases y 0 de 5 frases de otras voces lo lograron.
- Para interrumpir hay que hablar unos 2 segundos ("Espera, Azul, déjame decirte algo"); un "para" muy corto puede no alcanzar.
- No es seguridad de banco: una grabación de la voz del usuario podría pasar, y una voz parecida a veces también.
- Falta la prueba con la voz real del usuario; los umbrales se ajustan con los números del registro.

## Cómo revertirla
"Olvidar mi voz" en la app desactiva las interrupciones; borrar el modelo de hablantes las quita del todo.
