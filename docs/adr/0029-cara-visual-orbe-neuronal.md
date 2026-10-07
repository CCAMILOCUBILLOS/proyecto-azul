# 0029. La cara visual de Azul: orbe neuronal con subtítulos

- Estado: Aprobada (forma, paleta y texto elegidos por el usuario el 2026-10-05)
- Fecha: 2026-10-05
- Capa: 3 (interfaz)
- Tipo: B (reversible)

## Contexto
La app era una lista de burbujas de chat con una caja de texto. El usuario pidió una cara para Azul parecida a un cerebro de conexiones neuronales en azul, morado y negro, con luces que suben y bajan con el volumen de la voz de Azul y un movimiento muy suave mientras escucha. Envió dos videos de referencia (un cerebro de nodos luminosos y un orbe de voz tipo Jarvis). Se conservan el nombre, el azul de marca y el ícono del orbe.

## Opciones consideradas
- Forma: cerebro reconocible, **orbe neuronal**, u orbe que contiene un cerebro.
- Texto: **subtítulos** (frase actual), panel lateral, u oculto.
- Dibujo: Canvas 2D propio (sin dependencias) o una librería 3D (dependencia nueva).

## Decisión
El usuario eligió el **orbe neuronal** y los **subtítulos** (2026-10-05). Se dibuja con Canvas 2D, sin dependencias nuevas.
- Reposo: el orbe respira y gira despacio. Con "Oye Azul" activo aparece el anillo del ícono.
- Escuchando: respiración y giro suaves, con el anillo; sin destellos.
- Pensando: impulsos viajan hacia el núcleo. Buscando: impulsos violeta hacia afuera y la red se tiñe de violeta.
- Hablando: la luz nace en el núcleo y recorre la red hacia afuera, con la intensidad del volumen real de la voz (AnalyserNode en la reproducción).
- Subtítulos: tu frase (pequeña) y la de Azul (grande); el historial completo está detrás de un botón; escribir, detrás del botón de teclado.
- Respeta "reducir movimiento" del sistema.

## Consecuencias
- Positivas: el estado de la voz se ve de lejos; sin costo ni dependencias.
- Negativas o riesgos: el dibujo consume batería en el celular mientras la app está abierta (se pausa con la app en segundo plano). Rendimiento en el iPhone por confirmar con el usuario.

## Cómo revertirla
Volver a la versión anterior de `app/index.html`, `app/src/style.css` y `app/src/main.ts`, y quitar `app/src/orbe.ts`.

## Ajustes pedidos por el usuario (2026-10-06)
- Fondo negro total, como el vacío del espacio, con estrellas; Azul más grande.
- Anillo de barras que sigue el espectro de la voz y dos órbitas finas (inspirados en el segundo video).
- Los subtítulos se desvanecen 7 s después de que Azul queda en calma; siguen en el historial.
- Sin contador de gasto en la pantalla principal: el gasto del mes está en el panel del historial y arriba solo aparece el aviso desde 40 USD (el criterio 5 del MVP se mantiene).
- Sin nombre ni ícono en la franja superior: el orbe es la identidad en pantalla (el ícono sigue siendo el de la app).
