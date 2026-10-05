# 0023. Memoria con notas dentro de la respuesta

- Estado: Aprobada por el usuario el 2026-10-05 (mejora de velocidad A). Reemplaza la herramienta `remember` de las ADR 0010 y 0020.
- Fecha: 2026-10-05
- Capa: 3 (estructura interna)
- Tipo: B (reversible)

## Contexto
Con la herramienta `remember`, cada vez que Azul aprendía algo hacía falta una segunda llamada al cerebro (~5 s más). En el incremento 2, la mezcla "guardar + buscar" llegó a 25 s.

## Opciones consideradas
1. Mantener la herramienta `remember`.
2. Extraer los datos en segundo plano con otro modelo (+3 a 13 USD al mes), descartada por el usuario.
3. Que Azul anote los datos dentro de su propia respuesta.

## Decisión
Opción 3. Azul escribe `<recordar>dato en tercera persona</recordar>` al final de su respuesta. El núcleo (`core/notes.py`) quita esas notas del texto mientras llega por partes, antes de mostrarlo, decirlo en voz alta o guardarlo, y guarda cada dato en la memoria. También quita los espacios y saltos de línea justo antes de una nota.

## Consecuencias
- Prueba real del 2026-10-05: "me llamo Camilo y vivo en Villavicencio" guardó 2 datos con **una sola llamada** al cerebro.
- Riesgo: el modelo podría olvidar el formato. Una nota sin cerrar se descarta; nunca se muestra.
- Al aprender un dato, cambian las instrucciones y la siguiente respuesta rehace la caché (~3 ¢), igual que antes.

## Cómo revertirla
Volver a registrar la herramienta `remember` en `Conversation` y en `persona.py`.
