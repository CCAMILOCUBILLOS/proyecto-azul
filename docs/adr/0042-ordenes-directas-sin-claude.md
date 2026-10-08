# 0042. Órdenes directas: lo conocido se hace sin Claude

- Estado: Aprobada por el usuario el 2026-10-07
- Fecha: 2026-10-07
- Capa: 3 (flujo de cada mensaje)
- Tipo: B (reversible): `AZUL_ORDENES_DIRECTAS=false`

## Contexto
El usuario quiere que Azul viva en un "ecosistema" de programas que ya existen y
funcionan (Red Nacional, el correo), y que operarlos por orden suya no gaste créditos.
Medido el 2026-10-07: Claude $2,43 (150 llamadas por 69 mensajes) y Deepgram $0,95;
32 respuestas fueron para operar Red Nacional, y el precalentamiento de la caché costó
$1,15 de los $2,43.

## Opciones consideradas
1. Órdenes directas: catálogo + atajos aprendidos, sin IA.
2. Un modelo más barato (Haiku) para entender órdenes.
3. Un modelo local: no viable en el portátil (i3-4005U de 2014, 8 GB, sin GPU).

## Decisión (y quién la aprobó)
Opción 1, recomendada y elegida por el usuario.
- `RecepcionDeOrdenes` va antes de Claude en `Conversation.reply` (voz, app y WhatsApp
  del usuario). Reconoce órdenes que empiezan con la acción y preguntas fijas, más una
  fecha (hoy, ayer, "del 2 de octubre", "desde el 2 hasta el 5", "esta semana"). Si sobra
  cualquier otra cosa, va a Claude: así nada se ejecuta por confusión.
- Catálogo: agendamiento (y su simulación), lectura de correos, simulación, cargue,
  verificar, base, seguimiento, control, reporte, detener; resumen y progreso del
  tablero; itinerario de correos. Responde con frases fijas a partir de los datos.
- El cargue real pide "sí" antes (sin costo); cualquier otra respuesta lo cancela.
- Atajos aprendidos (tabla `atajos`): si Claude resolvió una orden corta (≤ 9 palabras)
  con un solo programa repetible y con respuesta fija, la frase queda guardada; las
  fechas de hoy/ayer se guardan como relativas. Nunca el cargue ni lo que tenga otras fechas.
- Lo directo queda en el historial (marca "orden directa") para que Claude tenga contexto.
- El precalentamiento ya no se hace si lo que se oye es una orden directa (decide con la
  frase terminada o con 6 palabras).
- Turnero (mismo incremento): si dos dispositivos oyen la misma pregunta, responde solo
  el primero (se medían dos turnos a 53 ms).

## Consecuencias
- Positivas: órdenes conocidas con costo de Claude cero e instantáneas; el catálogo crece
  solo con los atajos.
- Negativas: solo entiende frases parecidas a las del catálogo; las respuestas son fijas.
- La voz de Azul (Deepgram) sigue costando: es el 92 % del gasto de Deepgram (decisión aparte).

## Cómo revertirla
`AZUL_ORDENES_DIRECTAS=false` y reiniciar Azul; los atajos quedan en la tabla `atajos`.
