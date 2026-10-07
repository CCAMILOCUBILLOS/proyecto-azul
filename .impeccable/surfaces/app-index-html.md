---
version: 1
slug: "app-index-html"
primary_target: "app/index.html"
related_targets: ["app/src/main.ts","app/src/style.css"]
---

## Scope

Pantalla principal de la app de Azul (PWA): `app/index.html`, `app/src/`. Modo: Operate. Celular y PC por igual.

## Audience and job

Juan Camilo le habla a Azul y necesita saber, de un vistazo y a distancia, si Azul escucha, piensa, busca o habla. El texto es secundario: subtítulos de la frase actual; el historial completo detrás de un botón.

## Constraints

Se conservan: el nombre "Azul", el azul de marca (#3d8bff), el ícono del orbe. Paleta pedida por el usuario: azul, morado y negro. Sin dependencias nuevas (Canvas 2D). Toda la lógica de voz, chat de texto, "Oye Azul", gasto y clave sigue igual.

## Direction contract

THESIS: La cara de Azul es un orbe neuronal vivo: una esfera de nodos y sinapsis cuya luz es la voz de Azul. Rechaza el layout por defecto de app de chat (lista de burbujas con una caja de texto abajo como protagonista).

OWN-WORLD: Fondo casi negro con tinte índigo; sinapsis en azul eléctrico que viran a violeta y morado con la profundidad; núcleo blanco azulado. Texto claro tintado de azul; secundarios tintados de violeta, nunca gris. Controles redondos, finos, de trazo 1.75.

STORY: Al abrir, Azul está ahí, respirando. Al tocar el micrófono la red se mueve muy suave: escucha. Al pensar, impulsos viajan hacia el núcleo; al buscar, salen en violeta hacia afuera. Al hablar, la luz nace en el núcleo y recorre la red al ritmo del volumen de su voz.

FIRST VIEWPORT: Arriba, una franja mínima: orbe y "Azul" a la izquierda; "Oye Azul" y el gasto a la derecha. El orbe neuronal ocupa el centro; en celular lo limita el ancho (≈46 % del ancho de radio, unos 40–45 % del alto en 375×812) y el sobrante se reparte arriba y abajo del orbe. Debajo, el estado en una línea y los subtítulos (tu frase pequeña, la de Azul grande). Abajo, el micrófono grande centrado, con teclado a la izquierda e historial a la derecha.

FORM: Pedida por el usuario (orbe neuronal con iluminación según el volumen), sin tirada de concept-seed; seed key: ninguna (dirección fijada por el usuario).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Signature interaction

La luz de la voz se propaga del núcleo hacia afuera con retardo según la distancia (onda sináptica), y su intensidad sigue el volumen real de la voz de Azul (AnalyserNode). Escuchando: respiración lenta, rotación suave, sin destellos.
