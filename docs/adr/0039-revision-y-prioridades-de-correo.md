# 0039. Azul revisa los correos, los prioriza y alerta lo urgente

- Estado: Aprobada por el usuario el 2026-10-07
- Fecha: 2026-10-07
- Capa: 3 (tarea de fondo, memoria) y 4 (Outlook, WhatsApp)
- Tipo: B (reversible): `AZUL_CORREO_REVISAR=false`

## Contexto
El usuario pidió que Azul clasifique y revise sus correos, los organice por prioridad en
un itinerario con alertas, sin necesidad de verlo, y que aprenda sus prioridades
preguntándole al principio.

## Opciones consideradas
- Alertas: WhatsApp, voz en el portátil, notificación de Windows.
- Cuándo: urgente al momento + resúmenes; solo urgente; solo resúmenes.
- En Outlook: categorías de color, nada, mover a carpetas.
- Aprendizaje: repaso inicial + preguntas, o solo preguntas con lo nuevo.

## Decisión (y quién la aprobó)
El usuario eligió: alertas por **WhatsApp con texto y voz** ("preferiblemente en el cel":
una nota de voz con la voz de Azul), **solo lo urgente al momento**, **categorías de
color** en Outlook ("Azul: Urgente" rojo, "Alta" naranja, "Normal" azul, "Baja" gris) y
**repaso inicial + preguntas**.

Implementación:
- Cada 10 minutos (`AZUL_CORREO_REVISION_MINUTOS`) Azul lee los correos nuevos de la
  bandeja (asunto, remitente y ~400 caracteres del comienzo) y los clasifica con el cerebro
  aprobado (Sonnet, esfuerzo bajo) en tandas de 20, con números cortos en vez de los ids
  de Outlook. Resultado por correo: prioridad, acción, fecha límite y, si duda, una pregunta.
- Las reglas del usuario (`correo_reglas`) y lo que Azul sabe de él van en las instrucciones.
- Itinerario (`correo_clasificados`): lo abierto por prioridad y fecha; lo de prioridad baja
  se archiva. El usuario lo consulta hablando con Azul (`correo_itinerario`, `correo_hecho`).
- Las dudas (`correo_preguntas`) se le envían por WhatsApp y van en el contexto de Azul; la
  respuesta del usuario (`correo_prioridad`) se vuelve regla y recategoriza el correo.
- Repaso inicial a pedido del usuario (`correo_repaso_inicial`): hasta 14 días y 120
  correos, sin alertas, con una propuesta por remitente para que el usuario corrija.
- Si Azul estuvo apagada, al volver revisa como máximo las últimas 24 horas. Si el
  presupuesto del mes se agotó, no clasifica.

## Consecuencias
- Costo medido (2026-10-07): 0,6 centavos de dólar por revisión con correos nuevos, sin búsqueda web y sin vuelta extra (`busqueda_web=False`, `terminar_tras_herramientas=True`; antes 2,5 centavos). Unos 10 centavos al día, ~$3 al mes; el repaso inicial, ~10 centavos.
- Al sumar estas herramientas, Anthropic rechazó las solicitudes por exceso de herramientas en modo estricto ("compiled grammar is too large"): el modo estricto quedó solo para Red Nacional.
- Sin WhatsApp configurado no hay alertas al celular: lo urgente queda en el itinerario.
- Depende de Outlook clásico abierto y sin ventanas esperando (ver ADR 0037).
- El comienzo de cada correo nuevo pasa por Claude (Anthropic).

## Cómo revertirla
`AZUL_CORREO_REVISAR=false` en `.env` y reiniciar Azul; las categorías "Azul: …" se pueden
borrar desde Outlook (Categorizar → Todas las categorías).
