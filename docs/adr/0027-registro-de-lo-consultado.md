# 0027. Azul recuerda qué consultó de verdad

- Estado: Aprobada (corrección de un error de diseño; limpieza del historial aprobada por el usuario el 2026-10-05)
- Fecha: 2026-10-05
- Capa: 3
- Tipo: B (reversible)

## Contexto
- El historial se guardaba **solo como texto**, sin rastro de las herramientas usadas.
- Tras una alucinación real (un clima con "clima.com" sin consultar, antes de existir la herramienta del clima), se agregó la regla "no digas que consultaste algo si no usaste una herramienta".
- Consecuencia: Azul veía en su historial "lo busqué" sin pruebas y se acusaba en falso de haber mentido. El 2026-10-05 a las 15:26 hizo **1 búsqueda real** (el partido América–Llaneros) y un minuto después dijo que no la había hecho. Las falsas confesiones se acumularon en el historial y la volvían cada vez más desconfiada.

## Decisión
- Cada respuesta guarda en `messages.consulted` lo que se consultó de verdad: `búsqueda web` y/o `clima de <lugar>`. Esquema v2, con migración automática desde v1, incluidos los respaldos viejos.
- Al enviar el historial al cerebro, las respuestas con consultas llevan al final `⟦consultado: …⟧`. El usuario no lo ve.
- La personalidad explica la marca: lo que la tiene sí salió de una consulta real; no hay que disculparse ni corregir respuestas viejas, y el modelo nunca debe escribirla.
- La regla de honestidad sigue: consultar antes de dar datos actuales y no inventar fuentes.
- El registro de gasto anota `búsquedas: N` por llamada, para auditar.
- Con aprobación del usuario se borró el historial de conversación del 2026-10-05 (30 mensajes, con las falsas confesiones). Se conservaron los datos del usuario y el gasto. Respaldo previo: `azul-respaldo-2026-10-05_153424.zip`, en el portátil y en OneDrive.

## Consecuencias
- Azul puede distinguir lo que consultó de lo que no, también en turnos posteriores.
- Si el modelo llegara a escribir la marca por su cuenta, aparecería en el texto. Hay que vigilarlo; la personalidad lo prohíbe.

## Cómo revertirla
Dejar de llamar a `_for_brain` en `Conversation`. La columna `consulted` es inofensiva si no se usa.
