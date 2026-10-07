# 0028. Azul en el portátil: cliente de voz de escritorio

- Estado: Aprobada (activación y dependencias elegidas por el usuario el 2026-10-05) ("Oye Azul" ahora es local y de 24 horas: ADR 0035)
- Fecha: 2026-10-05
- Capa: 1 y 3
- Tipo: B (reversible)

## Contexto
El usuario quiere hablarle a Azul sin dejar la pantalla encendida. En el iPhone eso no es posible con una app web (ADR 0026). En el PC sí: un programa de escritorio puede usar el micrófono con la pantalla apagada, siempre que el equipo esté despierto.

## Opciones consideradas (activación)
1. "Oye Azul" siempre: costo según el ruido de la casa, hasta ~26 USD al mes.
2. Solo un atajo de teclado.
3. Ambos, con "Oye Azul" limitado a un horario (elegida).

## Decisión
- **Cliente de escritorio** (`azul.escritorio`, en Python), sin navegador:
  - captura el micrófono y reproduce por los parlantes con **miniaudio**;
  - atajo global **Ctrl+Alt+A** con **pynput**;
  - usa el mismo protocolo que la app (`/api/voz`), con reconexión automática.
- **Atajo:** empieza el modo conversación; si Azul escucha, envía ya; si habla, la calla.
- **"Oye Azul":** detector local (misma lógica que la app), solo dentro del horario (`AZUL_ESCRITORIO_DESDE` y `AZUL_ESCRITORIO_HASTA`; por defecto 07:00–22:00) y solo cuando Azul está libre.
- **Tonos de aviso:** agudo al empezar, grave al terminar la conversación.
- **Arranque:** `Iniciar Azul.cmd` lanza el núcleo y el cliente; al cerrar la ventana se apagan los dos. Su registro va a `datos/escritorio.log`.
- Se desactiva con `AZUL_ESCRITORIO_ACTIVO=false`; "Oye Azul" en el portátil, con `AZUL_ESCRITORIO_OYE_AZUL=false`.

## Ajustes de velocidad tras la prueba del usuario
- **Fin de frase decidido por Deepgram, también en "Oye Azul":** en un cuarto con ruido, el detector local no oía el silencio y un fragmento duró 17 s. Ahora el núcleo corta en cuanto Deepgram detecta el fin de la frase y avisa a la app y al portátil. En la prueba con ruido continuo cortó a los 4 s. También acorta (y abarata) las conversaciones ajenas.
- **Razonamiento bajo por defecto** (ADR 0014): el nivel medio solo con "explica", "por qué", "analiza"…; el alto con "a fondo" o "paso a paso". Antes, todo mensaje largo pensaba más, y por voz casi todo es largo.
- **Búsqueda web:** máximo 2 por respuesta (antes 3), y la instrucción de hacer una sola cuando baste. Cada búsqueda tarda 8–12 s; ese tiempo no se puede evitar.

## Consecuencias
- Probado por el usuario: "se activa bien".
- El atajo no funciona con el equipo bloqueado (Windows lo impide). "Oye Azul" con el equipo bloqueado está sin verificar.
- Costo de "Oye Azul" en el portátil: los fragmentos con voz cercana dentro del horario se envían a Deepgram.
- Corrección (2026-10-05): el tono de "te escucho" se borraba al empezar el turno, así que tras decir solo "Oye Azul" no sonaba nada y, sin pregunta en 8 s, Azul se apagaba en silencio. Ahora el tono suena después de empezar el turno y, si no se oye nada, suena el tono de cierre. Los registros indican cómo termina cada turno (sin el contenido).

## Cómo revertirla
`AZUL_ESCRITORIO_ACTIVO=false`, o quitar la línea `start … azul.escritorio` de `Iniciar Azul.cmd`.
