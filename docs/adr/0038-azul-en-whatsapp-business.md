# 0038. Azul en WhatsApp Business, aprendiendo permisos del usuario

- Estado: Aprobada por el usuario el 2026-10-07 (pendiente de configurar en Meta)
- Fecha: 2026-10-07
- Capa: 1 (exposición a internet con Tailscale Funnel), 3 (permisos) y 4 (Meta)
- Tipo: B (reversible): vaciar las variables AZUL_WHATSAPP_* y apagar el Funnel

## Contexto
El usuario quiere que Azul responda WhatsApp por él, sola con algunos contactos, y que
lo conozca. Se explicaron tres caminos: exportar chats (sin riesgo, no automático),
vincular su número como WhatsApp Web (no oficial: riesgo real de bloqueo del número) y
WhatsApp Business oficial de Meta (legal, pero con un número aparte).

## Opciones consideradas
- Camino: A exportar, B vincular (número propio o secundario), C WhatsApp Business.
- Recepción de mensajes: Tailscale Funnel hacia un puerto aparte, o un relevo en la nube.
- Con terceros: solo conversar; conversar + consultas; o "lo mismo que con el usuario".

## Decisión (y quién la aprobó)
El usuario eligió:
- **WhatsApp Business (Cloud API de Meta)** con un número propio para Azul (lo consigue;
  mientras tanto, el número de prueba de Meta).
- **Tailscale Funnel** hacia un receptor aparte (puerto 8720) que solo tiene `/whatsapp`;
  cada aviso se comprueba con la firma de la app de Meta (`X-Hub-Signature-256`).
- Lo usarán él y gente cercana, y también clientes o trabajo.
- Cuando escribe alguien sin regla, **Azul le escribe al usuario a su WhatsApp** con la
  respuesta propuesta; el usuario contesta «sí», «no» o la corrección.
- Con terceros, **lo mismo que con el usuario, pero aprendido**: cada herramienta pide
  permiso hasta que el usuario enseñe una regla («siempre»), **también las acciones**
  (el usuario lo eligió sabiendo que se recomendaba preguntar siempre por ellas).

Implementación:
- Cada contacto tiene su propia conversación (tabla `wa_mensajes`); ve los datos del
  usuario más lo aprendido del contacto (`wa_datos`).
- Reglas por contacto y herramienta (`wa_reglas`); "responder" = responder sin consultar.
- Pendientes (`wa_pendientes`) que el usuario resuelve hablando con Azul por WhatsApp, la
  app o la voz (herramienta `whatsapp_decidir`); van en el contexto de Azul.
- Pasadas 24 h sin que el usuario escriba, WhatsApp solo permite una plantilla aprobada:
  Azul la envía (máximo una cada 6 h) y el detalle se ve cuando el usuario responda.
- Mensajes repetidos por Meta se descartan (`wa_vistos`). Los registros no guardan textos.

## Consecuencias
- Positivas: legal, sin riesgo para el número personal; Azul aprende y pregunta cada vez menos.
- Negativas: número aparte; Azul no ve el WhatsApp personal; el portátil debe estar
  encendido; las respuestas a terceros cuestan como cualquier mensaje a Claude.
- Riesgos: una regla amplia para una acción (p. ej. ejecutar en Red Nacional) deja que ese
  contacto la dispare sin preguntar; los mensajes de terceros pasan por Anthropic. El
  receptor queda en internet (solo `/whatsapp`, con firma obligatoria).
- Notas de voz, imágenes y documentos aún no se entienden: Azul lo dice.

## Cómo revertirla
Vaciar `AZUL_WHATSAPP_*` en `.env`, `tailscale funnel reset` y reiniciar Azul.
