# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Una sola persona: Juan Camilo, el dueño de Azul. Habla en español (Colombia) y no programa. Usa Azul por igual en el iPhone (app instalada, con datos móviles o Wi-Fi) y en el navegador del portátil, casi siempre conversando por voz.

## Product Purpose
Azul es su asistente personal de voz, inspirado en J.A.R.V.I.S.: conversa de cualquier tema, recuerda datos entre días, busca en internet y consulta el clima, y crece con nuevas capacidades que el usuario elige una a una (ADR 0017). Funciona cuando puede hablarle y le responde por voz en pocos segundos, sin pasos de más.

## Positioning
No es un chat genérico: es un asistente propio, con memoria personal y un costo mensual controlado (tope de 50 USD), que vive en su portátil y le contesta desde cualquier lugar por su red privada.

## Operating Context
- iPhone: modo conversación de un toque (Azul vuelve a escuchar tras cada respuesta hasta una despedida, ■ o 8 s de silencio) y "Oye Azul" con la app abierta.
- Portátil: cliente de escritorio sin pantalla (Ctrl + Alt + A y "Oye Azul" de 07:00 a 22:00); la app web abierta en el navegador es la cara visual.
- Estados de voz que la interfaz refleja: escuchando, pensando, buscando, hablando, en espera.
- Clave de acceso una sola vez por dispositivo; el portátil no la pide.

## Capabilities and Constraints
- Conversación por voz y por texto, historial, gasto del mes con aviso a 40 USD y bloqueo a 50 USD, interruptor de "Oye Azul" con indicador de nivel, orden de parada.
- App web instalable (PWA, Vite + TypeScript, sin framework), servida por el núcleo en el portátil.
- Mientras habla, el estado de la voz domina la pantalla; el texto de la conversación queda en segundo plano (decisión del usuario, 2026-10-05).
- Los aplausos no funcionan como activación en su contexto: no son parte del producto.

## Brand Commitments
- El nombre "Azul".
- El azul como color de la marca.
- El ícono actual: el orbe (círculo azul) del ícono de la app y junto al nombre.
- Voz cercana y casual en español; la voz hablada es Gloria (Deepgram Aura-2).

## Evidence on Hand
- Ícono actual: `app/public/icono.svg` y sus PNG.
- Dos videos de referencia del usuario (Downloads, 2026-10-05): uno con un cerebro de nodos y conexiones luminosas; otro con un orbe tipo Jarvis que reacciona a la voz. No hay testimonios, métricas públicas ni otros recursos de marca.

## Product Principles
- La voz primero: en cada momento debe ser obvio si Azul escucha, piensa o habla.
- Honestidad: Azul no inventa datos ni fuentes, y la interfaz no simula actividad que no ocurre.
- Sin fricción: un toque para hablar, nada de pasos de más.
- Lo personal se queda en casa: memoria y datos viven en el portátil.

## Accessibility & Inclusion
Sin requisitos específicos confirmados. Español como único idioma de la interfaz.
