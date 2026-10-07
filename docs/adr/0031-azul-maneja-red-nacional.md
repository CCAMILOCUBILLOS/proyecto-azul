# 0031. Azul maneja el tablero de Red Nacional

- Estado: Aprobada (alcance, autonomía, datos y conexión elegidos por el usuario el 2026-10-06)
- Fecha: 2026-10-06
- Capa: 1 (conexión entre equipos), 3 (permisos) y 4 (integración)
- Tipo: B (reversible): se quita `AZUL_RED_NACIONAL_URL` y Azul deja de ofrecer las herramientas

## Contexto
El usuario trabaja con RedNacional (Confianza IPS): un programa propio con un tablero (`Tablero.bat` → `tablero.py`, en `localhost:8765`) que lee correos de Outlook, prepara agendamientos con IPS aliadas, crea órdenes en Biofile y lleva seguimiento, tarifas, ventas y el control en SharePoint. Corre en el PC de Optometría, que no tiene micrófono ni parlantes: el usuario quiere dar las órdenes desde el celular o el portátil y que se ejecuten allá. Más adelante ese PC se cambiará por uno con audio.

## Opciones consideradas (conexión)
1. **Tailscale en el PC de Optometría** y publicar el tablero solo dentro de la red privada (`tailscale serve`).
2. Tailscale + un "puente" de Azul en ese PC (podría abrir Tablero.bat solo).
3. Llevar RedNacional al portátil (riesgo de duplicar órdenes con dos equipos).

## Decisión
- Conexión: opción 1 (el usuario puede instalar Tailscale en ese PC).
- Alcance: todo lo que el usuario pida. Dos herramientas para el cerebro: `red_nacional_consultar` (resumen, seguimiento, progreso, ventas, control, directorio, clientes…) y `red_nacional_ejecutar` (simulación, verificación, cargue real, correos, agendar, base, ventas, control, seguimiento, reporte, detener). Usan las mismas rutas que los botones del tablero; RedNacional no se modifica.
- Autonomía total, como el ADR 0012, también en el cargue real. Azul dice siempre en voz alta qué lanzó y si fue real o simulación; solo pregunta si la orden es ambigua entre simular y cargar. El número de confirmación que exige el tablero para el cargue lo calcula Azul con las órdenes pendientes en ese momento.
- Datos: Azul puede ver nombres y cédulas (decisión del usuario, advertido de que son datos sensibles según la Ley 1581 y de que van a Anthropic para responder).

## Consecuencias
- Prueba real con el tablero simulado (2026-10-06): Sonnet 5.5 consultó el resumen y lanzó la simulación correctamente.
- Requisitos que no cambian: el PC de Optometría prendido con Tablero.bat abierto; la sesión de Biofile la inicia el usuario; leer correos exige el Outlook clásico abierto.
- Los procesos corren en segundo plano: Azul cuenta cómo van si se le pregunta (no avisa sola al terminar).
- "Azul, para" calla a Azul; para detener un proceso del tablero hay que pedirlo ("detén el cargue").
- Respuestas largas del tablero se recortan a 12 000 caracteres para cuidar el costo.
- Riesgo: una orden mal entendida por voz puede lanzar un proceso real; se mitiga con el anuncio en voz alta y la pregunta ante ambigüedad.
- El tablero publicado no tiene clave: lo puede abrir cualquier dispositivo de la red privada del usuario (solo los suyos). Sus botones de acción rechazan peticiones de otras páginas web, así que desde el navegador del celular el tablero se ve pero no lanza procesos.

## Cómo revertirla
Borrar `AZUL_RED_NACIONAL_URL` del `.env` y reiniciar Azul; en el PC de Optometría, `tailscale serve --https=443 off`.
