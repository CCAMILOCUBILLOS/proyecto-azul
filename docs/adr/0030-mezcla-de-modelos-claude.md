# 0030. Mezcla de modelos Claude: Sonnet para lo cotidiano, Opus para lo difícil

- Estado: Aprobada (el usuario eligió "mezcla Claude" y Sonnet 5.5 el 2026-10-06)
- Fecha: 2026-10-06
- Capa: 2
- Tipo: B (reversible): el cerebro es un adaptador; volver es cambiar la configuración

## Contexto
El usuario quiere que cada respuesta cueste menos. Del 1 al 6 de octubre Azul gastó 2,05 USD (1,65 el cerebro, 0,40 la voz), unos 2,4 ¢ por respuesta con Opus 5.5. Un modelo local no es viable en el portátil (i3 de 2 núcleos, 8 GB, sin tarjeta gráfica: 30 a 60 s por respuesta).

## Opciones consideradas
1. Seguir con Opus 5.5 y solo ahorrar con la caché (~9–12 USD/mes estimados).
2. **Mezcla Claude**: un modelo económico para lo cotidiano y Opus para lo difícil (~3–6 USD/mes).
3. DeepSeek, directo o por otro proveedor (~0,5–2 USD/mes): datos personales en China y usados para entrenar por defecto (si es directo); sin búsqueda web propia; habría que rehacer varias piezas.
4. Modelo local en un equipo nuevo con tarjeta gráfica (costo de compra, menos inteligencia).

Para lo cotidiano se compararon Sonnet 5.5 (la mitad del precio de Opus, mismas funciones) y Haiku 4.5 (un cuarto, generación anterior, sin varias funciones que Azul usa).

## Decisión
Opción 2 con **Claude Sonnet 5.5** para lo cotidiano (esfuerzo bajo o medio) y **Claude Opus 5.5** cuando el pedido trae señales de "pensar a fondo" (esfuerzo alto, ADR 0014). La elección del modelo vive en el adaptador: el núcleo solo pide cuánto pensar. Configurable con `AZUL_BRAIN_MODEL` y `AZUL_BRAIN_MODEL_DEEP`.

Ahorro gratis aplicado a la vez: la ventana del historial (40 a 59 mensajes) mueve su inicio de a 20 mensajes, así el historial queda en la caché del proveedor y solo se reescribe una vez cada 10 turnos.

## Consecuencias
- Prueba real (2026-10-06): respuesta corta con Sonnet 5.5 a 0,21 ¢ y primer texto en 1,4 s.
- Cada modelo tiene su propia caché: las respuestas a fondo con Opus pagan escribir la suya.
- Riesgo: que Sonnet se sienta menos agudo en alguna conversación; el usuario puede pedir "piénsalo a fondo" o volver a Opus en la configuración.

## Cómo revertirla
En `.env`: `AZUL_BRAIN_MODEL=claude-opus-5-5` y reiniciar Azul.
