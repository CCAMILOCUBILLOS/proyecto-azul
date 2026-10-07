---
name: Azul
description: La cara de un asistente de voz personal; un orbe neuronal vivo cuya luz es la voz de Azul.
colors:
  azul: "#3d8bff"
  azul-claro: "#96c4ff"
  violeta: "#8b5cf6"
  morado: "#c084fc"
  nucleo: "#ebf4ff"
  fondo: "#000000"
  fondo-indigo: "#0d0b2e"
  fondo-alto: "#0a0a1f"
  superficie: "#0f1030"
  usuario: "#1b2a6b"
  borde: "#23255a"
  borde-suave: "#181a44"
  texto: "#e9edff"
  suave: "#9ea6d9"
  tenue: "#6f73b0"
  aviso: "#ffcf7a"
  error: "#ff8f86"
typography:
  display:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif"
    fontSize: "clamp(1.1rem, 1rem + 0.6vw, 1.4rem)"
    fontWeight: 500
    lineHeight: 1.42
  headline:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 650
    letterSpacing: "0.08em"
  title:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 600
    lineHeight: 1.45
  body:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 550
  caption:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    fontFeature: "\"tnum\""
rounded:
  cola: "6px"
  burbuja: "18px"
  dialogo: "20px"
  control: "23px"
  pastilla: "999px"
  circulo: "50%"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  boton-microfono:
    textColor: "{colors.texto}"
    rounded: "{rounded.circulo}"
    size: "74px"
  boton-microfono-escuchando:
    backgroundColor: "{colors.azul}"
    textColor: "{colors.texto}"
    rounded: "{rounded.circulo}"
  boton-microfono-respondiendo:
    textColor: "{colors.morado}"
    rounded: "{rounded.circulo}"
  boton-redondo:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.suave}"
    rounded: "{rounded.circulo}"
    size: "46px"
  boton-redondo-hover:
    textColor: "{colors.texto}"
  boton-primario:
    backgroundColor: "{colors.azul}"
    textColor: "#ffffff"
    rounded: "{rounded.control}"
    padding: "0 18px"
    height: "46px"
  boton-parar:
    backgroundColor: "{colors.violeta}"
    textColor: "#ffffff"
    rounded: "{rounded.control}"
    height: "46px"
  interruptor-oye-azul:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.suave}"
    typography: "{typography.label}"
    rounded: "{rounded.pastilla}"
    padding: "0 14px"
    height: "34px"
  campo-texto:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.texto}"
    rounded: "{rounded.control}"
    padding: "12px 16px"
    height: "46px"
  burbuja-usuario:
    backgroundColor: "{colors.usuario}"
    textColor: "{colors.texto}"
    rounded: "{rounded.burbuja}"
    padding: "10px 14px"
  burbuja-azul:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.texto}"
    rounded: "{rounded.burbuja}"
    padding: "10px 14px"
  dialogo-clave:
    backgroundColor: "{colors.fondo-alto}"
    textColor: "{colors.texto}"
    rounded: "{rounded.dialogo}"
    padding: "28px 24px"
---

# Design System: Azul

## Overview

**Creative North Star: "La luz es la voz"**

La cara de Azul es un orbe neuronal vivo: una esfera de nodos y sinapsis dibujada en Canvas 2D, suspendida sobre un fondo casi negro con tinte índigo. Todo lo demás en la pantalla es secundario a esa esfera. Su luz no decora: dice el estado de la voz. En reposo respira y su núcleo blanco azulado sigue encendido; al escuchar respira más hondo y gira despacio; al pensar los impulsos viajan hacia el núcleo; al buscar salen hacia afuera y la red entera vira a violeta; al hablar la luz nace en el núcleo y recorre la red con el volumen real de la voz.

La densidad es mínima. Una franja superior lleva el ícono, el nombre y el interruptor "Oye Azul"; el centro es del orbe; debajo, una línea de estado y los subtítulos de la frase actual; abajo, un micrófono grande y dos controles redondos. El historial completo vive detrás de un botón, en un panel lateral. Esto rechaza de forma deliberada el diseño por defecto de app de chat (una lista de burbujas con la caja de texto como protagonista).

El material es luz sobre oscuridad: brillos radiales, mezcla aditiva y halos que se apagan antes del borde. No hay tarjetas ni superficies apiladas en la vista principal; los controles son finos, redondos y de trazo 1.75.

**Key Characteristics:**
- Un solo protagonista: el orbe neuronal, que refleja seis estados (reposo, atento, escuchando, pensando, buscando, hablando).
- Paleta de tres luces sobre negro índigo: azul eléctrico, violeta y morado, con núcleo blanco azulado.
- Texto claro tintado de azul; secundarios tintados de violeta, nunca grises neutros.
- Formas redondas: círculos, pastillas y radios generosos; ningún ángulo recto visible en un control.
- Movimiento lento y continuo, con una sola curva de transición y respeto por `prefers-reduced-motion`.

## Colors

Tres luces (azul, violeta, morado) sobre un negro con tinte índigo; la temperatura del color dice qué hace Azul.

### Primary
- **Azul eléctrico de marca** (azul): el color de la marca, compromiso de producto. Sinapsis delanteras del orbe, anillo del ícono, borde del micrófono, botón Enviar, foco de los campos y relleno de nivel del interruptor "Oye Azul". Es la luz de escuchar y hablar.
- **Azul hielo** (azul-claro): centro de los nodos azules, impulsos, anillo de foco (`:focus-visible`), cursor del campo de texto y color de la línea de estado mientras escucha.

### Secondary
- **Violeta sináptico** (violeta): profundidad. Las sinapsis del fondo de la esfera viran a violeta; al buscar, la red entera se tiñe de él. En la interfaz, el botón Parar y la selección de texto.

### Tertiary
- **Morado eléctrico** (morado): pensamiento y búsqueda. Impulsos violeta, nodos morados (alrededor del 30 % de la red), línea de estado al pensar o buscar, ícono del orbe al pensar o buscar, anillo del modo conversación y el micrófono mientras Azul responde.

### Neutral
- **Núcleo blanco azulado** (nucleo): solo el corazón del orbe y los nodos de máxima energía. Nunca como fondo ni como texto.
- **Negro del vacío** (fondo): negro total, como el espacio; fondo de la app y `theme-color`. Sobre él, el lienzo dibuja estrellas (polvo apenas visible y unas pocas estrellas que titilan, con una deriva lentísima y, de vez en cuando, una estrella fugaz). El **índigo profundo** (fondo-indigo) ya no tiñe el fondo; queda solo en el halo del orbe.
- **Noche elevada** (fondo-alto): diálogo de la clave de acceso.
- **Superficie índigo** (superficie): burbujas de Azul en el historial y, translúcida (60–75 %), fondo de controles y campos.
- **Azul tinta** (usuario): burbujas del usuario en el historial.
- **Borde índigo** (borde) y **borde tenue** (borde-suave): contornos de controles y campos; divisiones del historial.
- **Blanco azulado** (texto): texto principal y la frase de Azul en los subtítulos.
- **Lavanda suave** (suave): texto secundario, la frase del usuario, íconos en reposo.
- **Lavanda tenue** (tenue): texto terciario, el gasto del mes (solo en el historial), placeholders, la línea "Di «Oye Azul»".
- **Ámbar de aviso** (aviso) y **coral de error** (error): solo mensajes de estado; nunca decoración.

### Named Rules
**The Luz Es Estado Rule.** El azul significa escuchar y hablar; el violeta y el morado significan pensar y buscar. Un color de luz no se usa en un estado que no le corresponde, ni en el orbe ni en los controles que lo acompañan.

**The Sin Gris Rule.** Los textos y bordes secundarios están tintados de índigo o violeta. No se introduce un gris neutro.

## Typography

**Display Font:** pila del sistema (`system-ui`: Segoe UI en Windows, San Francisco en iPhone), con Roboto y sans-serif como respaldo.
**Body Font:** la misma pila del sistema.

**Character:** Una sola familia, sobria, que no compite con el orbe. La jerarquía la dan el tamaño, el peso y el color, no un contraste de familias. La elección definitiva de la fuente de títulos está abierta (ver Do's and Don'ts).

### Hierarchy
- **Display** (500, clamp(1.1rem, 1rem + 0.6vw, 1.4rem), 1.42): la frase actual de Azul en los subtítulos, centrada, hasta 36rem, con `text-wrap: balance`.
- **Headline** (650, 1.15rem, espaciado 0.08em): el nombre "Azul" junto al ícono. El título del diálogo de clave usa 1.4rem y el del historial 1rem/600.
- **Title** (600, 0.95rem, 1.45): la línea de estado de la voz ("Te escucho…", "Pensando…", "Buscando en internet…", "Di «Oye Azul»"), en mayúscula inicial de oración, nunca en versalitas ni en mayúsculas.
- **Body** (400, 0.95rem, 1.45): la frase del usuario en los subtítulos (hasta 34rem) y el texto del historial.
- **Label** (550, 0.85rem): el interruptor "Oye Azul".
- **Caption** (400, 0.75rem, cifras tabulares): el gasto del mes, dentro del panel del historial; arriba solo aparece el aviso de gasto (desde 40 USD) o el de conexión.

### Named Rules
**The Tu Frase Pequeña Rule.** En los subtítulos la frase de Azul es grande y clara (display, texto); la del usuario es pequeña y suave (body, suave). La jerarquía nunca se invierte.

**The 16px Rule.** Los campos de escritura usan 16px exactos para que el iPhone no haga zoom.

## Layout

Una columna centrada en una retícula de cuatro filas a toda la altura (`100dvh`): franja superior, escena (orbe y subtítulos), entrada de texto plegable y pie de controles. Contenedor máximo de 1120px para la franja y la escena; 40rem para subtítulos y entrada; 22rem para el pie. Márgenes laterales de 16px y respeto de las zonas seguras (`safe-area-inset`).

El lienzo cubre toda la ventana, detrás de la interfaz; el orbe vive en la escena (entre la franja superior y los controles). Su radio es `min(38 % del ancho, 34 % del alto disponible)`, para que quepan el anillo de barras y las órbitas. Cuando hay subtítulos, el orbe sube y se reduce un poco con un deslizamiento suave; cuando se van, vuelve al centro. Los subtítulos flotan al pie de la escena y se desvanecen 7 s después de que Azul queda en calma (siguen en el historial).

El pie es una retícula 1fr–auto–1fr: teclado a la izquierda, micrófono al centro, historial a la derecha, con 24px entre ellos. El historial es un panel lateral de hasta 440px que, por debajo de 560px, ocupa la pantalla completa y entra desde abajo.

Ritmo de espacios: 6, 8, 12, 16 y 24px; los subtítulos reservan 7.5rem de alto para que la pantalla no salte al cambiar de frase.

## Elevation & Depth

La profundidad es luz, no sombra de papel. El orbe usa mezcla aditiva (`lighter`), brillos radiales y un halo índigo que crece con el volumen de la voz. En la interfaz, las "sombras" son resplandores de color: el ícono del orbe y el micrófono emiten un brillo azul o morado según el estado. Solo las capas que se superponen (historial y diálogo) llevan una sombra negra amplia y difusa.

### Shadow Vocabulary
- **Brillo del ícono** (`box-shadow: 0 0 10px rgb(61 139 255 / 55%)`; escuchando o hablando `0 0 16px rgb(150 196 255 / 80%)`; pensando o buscando `0 0 14px rgb(192 132 252 / 70%)`): el ícono acompaña la luz del orbe.
- **Micrófono en reposo** (`box-shadow: 0 6px 24px rgb(20 30 120 / 45%)`): lo despega del fondo.
- **Micrófono escuchando** (`box-shadow: 0 6px 24px rgb(61 139 255 / 50%), 0 0 0 6px rgb(61 139 255 / 18%)`): anillo de luz que respira de 6 a 11px cada 3.2s.
- **Micrófono mientras Azul habla** (`box-shadow: 0 6px 28px rgb(61 139 255 / 45%), 0 0 0 6px rgb(139 92 246 / 16%)`).
- **Capa superpuesta** (`box-shadow: -24px 0 60px rgb(0 0 0 / 55%)` en el historial; `0 24px 60px rgb(0 0 0 / 60%)` en el diálogo).

### Named Rules
**The Brillo No Sombra Rule.** Los controles de la vista principal brillan con el color de su estado; no llevan sombras negras ni desplazadas. La sombra negra es exclusiva de las capas que tapan la escena.

## Shapes

Todo es redondo. Los controles de acción son círculos (micrófono de 74px, botones de 46px), el interruptor "Oye Azul" es una pastilla, y los campos y botones de texto tienen radio igual a la mitad de su alto (23px sobre 46px). Las burbujas del historial tienen 18px con una esquina de 6px del lado de quien habla. El diálogo tiene 20px. Los bordes son de 1px (1.5px en el micrófono y su anillo de conversación) y los íconos son SVG de línea, trazo 1.75, extremos y uniones redondeados. El ícono de marca es un anillo con un núcleo sólido; el anillo del orbe en estado atento retoma esa forma.

## Components

### Micrófono (componente firma)
Grande, central, el único control que se presiona a ciegas.
- **Forma:** círculo de 74px, borde de 1.5px azul, fondo radial índigo oscuro (`#16185a` a `#0b0b26`), ícono de 28px.
- **Escuchando:** fondo radial azul brillante, borde azul hielo, anillo de luz que respira (desactivado con movimiento reducido).
- **Respondiendo:** borde e ícono morados; el ícono cambia a un cuadrado de detener relleno.
- **Modo conversación:** anillo morado de 1.5px a 7px por fuera, que avisa que Azul volverá a escuchar sola.
- **Toque:** sin selección de texto ni menú contextual al mantener presionado.

### Botones redondos
- **Forma:** círculo de 46px, borde índigo de 1px, fondo de superficie al 60 %, ícono de línea de 22px en lavanda suave.
- **Hover / abierto:** borde azul y texto blanco azulado, transición de 0.25s.

### Interruptor "Oye Azul"
- **Forma:** pastilla de 34px de alto con un punto de 7px a la izquierda.
- **Activo:** borde azul; el fondo se llena de izquierda a derecha con el nivel del micrófono (`--nivel`); el punto se enciende en azul hielo con brillo.
- **Enviando:** el borde, el relleno y el punto pasan a morado.

### Botones de texto
- **Enviar / Entrar:** pastilla de 46px de alto, fondo azul, texto blanco 600. Hover un azul más claro.
- **Parar:** misma forma, fondo violeta.

### Campos
- **Estilo:** pastilla de 46px mínimo, borde índigo de 1px, fondo de superficie al 75 % (en el diálogo, fondo negro índigo), texto de 16px, cursor azul hielo.
- **Foco:** el borde pasa a azul; sin anillo adicional. Los demás elementos usan un anillo azul hielo de 2px a 3px de distancia.
- **Error:** mensaje en coral bajo el campo.

### Subtítulos y línea de estado
- **Línea de estado:** una sola línea en peso 600, azul hielo al escuchar, morado al pensar o buscar, lavanda tenue en atento; vacía en reposo y al hablar.
- **Subtítulos:** la frase del usuario pequeña y suave; la de Azul grande y clara; los avisos en ámbar a 0.95rem.

### Historial
- **Panel:** lateral derecho, fondo negro índigo al 96 %, borde izquierdo tenue, entra deslizándose 40px con opacidad (0.45s).
- **Burbujas:** usuario en azul tinta a la derecha; Azul en superficie con borde tenue a la izquierda; avisos centrados en ámbar sin fondo.

### Orbe neuronal
Entre 280 y 420 nodos (68 % en la superficie de una esfera de Fibonacci con desorden, el resto denso hacia el núcleo), tres vecinos por nodo y axones largos de la superficie al interior. Sinapsis curvas combadas hacia el núcleo; atrás violeta, adelante azul. Los estados se mezclan sin saltos (suavidad exponencial de 2.4/s). Al hablar, el volumen se comprime, tiene un piso de 0.24 para que las pausas entre palabras no parezcan reposo, y la onda llega del núcleo al borde en 0.42s. Con movimiento reducido: sin respiración ni destellos, giro al 15 % e impulsos al 30 %.

## Do's and Don'ts

### Do:
- **Do** dejar que el orbe sea el protagonista: cualquier pantalla nueva de voz pone el orbe al centro y el texto en segundo plano.
- **Do** usar azul para escuchar y hablar, y violeta o morado para pensar y buscar, en el orbe y en los controles que lo acompañan.
- **Do** mantener el núcleo blanco azulado encendido en todos los estados, también en reposo.
- **Do** hacer que los halos y anillos del lienzo se apaguen dentro del lienzo, sin cortes rectos.
- **Do** usar la curva `cubic-bezier(0.16, 1, 0.3, 1)` en todas las transiciones de la interfaz.
- **Do** escribir la línea de estado en mayúscula inicial de oración, con puntos suspensivos cuando la acción está en curso.
- **Do** conservar el ícono de marca tal como está (anillo y núcleo azules sobre fondo `#0b1d3a`).

### Don't:
- **Don't** volver al diseño de app de chat, con una lista de burbujas y la caja de texto como protagonista en la vista principal.
- **Don't** usar grises neutros para texto o bordes secundarios.
- **Don't** mostrar actividad que no ocurre: el orbe no simula hablar, pensar ni buscar fuera de esos estados.
- **Don't** usar el núcleo blanco azulado como fondo o como color de texto.
- **Don't** usar ámbar o coral fuera de avisos y errores.
- **Don't** tomar la pila de fuentes del sistema como decisión cerrada de la fuente de títulos: sigue abierta hasta que el usuario apruebe alojar una fuente propia.

## Anillo de la voz y órbitas

- **Anillo de barras** (120 barras, a 1.17 radios del centro, simétrico): en reposo son marcas finas; con "Oye Azul" se ven más; escuchando, una ola lenta da la vuelta; pensando o buscando, un barrido gira como un radar; hablando, cada barra sigue el espectro real de la voz de Azul (AnalyserNode), con los graves arriba. Azul hacia violeta según el estado.
- **Órbitas**: dos elipses finas e inclinadas (azul hielo y morado) a 1.32 radios, con su mitad trasera detrás de la red y un punto de luz que viaja por cada una. Brillan más cuando Azul habla.
- **Franja superior**: sin nombre ni ícono, por decisión del usuario (2026-10-06); solo el interruptor "Oye Azul" a la derecha. El orbe es la identidad en pantalla.
