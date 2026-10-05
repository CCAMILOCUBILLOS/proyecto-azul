# 0016. Alcance del MVP (v0.1): "Azul conversa y recuerda"

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: transversal
- Tipo: B (reversible)

## Incluye
1. Una app web instalable (Android, iPhone y PC) con botón para hablar, chat de texto y botón de parada.
2. Conversación por voz en cadena (Deepgram → Opus 5.5 → Deepgram), con la respuesta transmitida por partes.
3. Memoria: el historial y los datos importantes sobre el usuario, extraídos automáticamente.
4. Orden de parada por voz y por botón.
5. Acceso seguro: Tailscale más una clave de la app.
6. Control de gasto: límite de 50 USD al mes, con aviso a los 40 (R3).
7. Portabilidad: los datos en `datos/` y un comando de respaldo (R1).
8. Arranque con un solo comando o un doble clic.
9. Búsqueda web (ADR 0015).

Personalidad: **cercana y casual**; tutea al usuario (R2).

## No incluye
La activación por voz (v0.2), acciones sobre correo, agenda o PC, documentos, la casa inteligente y el funcionamiento con el portátil apagado.

## Criterios de terminado
1. Desde iPhone y Android, incluso fuera de casa, el usuario le habla y Azul responde por voz en español.
2. Empieza a responder en unos 2 a 3 segundos (es una meta, se medirá).
3. Recuerda entre conversaciones de días distintos.
4. "Azul, para" corta la respuesta de inmediato.
5. Se puede ver el gasto del mes, y el límite funciona.
6. Un respaldo restaurado conserva la memoria intacta.
