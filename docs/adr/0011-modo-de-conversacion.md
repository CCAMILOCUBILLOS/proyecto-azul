# 0011. Modo de conversación: tocar para hablar, y "Oye Azul" en v0.2

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 3 (estructura interna)
- Tipo: B (reversible)

## Contexto
El usuario prefiere activar a Azul por voz, pero quiere llegar pronto al primer logro.

## Opciones consideradas
1. Tocar para hablar.
2. Manos libres con la app abierta.
3. Ambos, con un interruptor.
4. Activación por voz con una palabra (esta opción la pidió el usuario).

## Decisión
- **MVP (v0.1):** tocar para hablar, más un chat de texto para pruebas. La comunicación entre la app y el núcleo va por WebSocket.
- **v0.2:** la palabra de activación **"Oye Azul"**, detectada dentro del propio dispositivo. Funciona en el celular con la app abierta y la pantalla encendida, y en el portátil incluso en segundo plano.

## Consecuencias
- Con una app web, el celular no puede escuchar con la pantalla bloqueada. Un atajo posible es "Oye Siri, abre Azul" o una rutina de Google Assistant.
- El motor de detección de la palabra está por elegir en la v0.2; una de las opciones requiere crear una cuenta.

## Cómo revertirla
Es una configuración de la app y del núcleo.
