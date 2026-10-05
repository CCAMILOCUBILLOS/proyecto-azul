# Supuestos

| # | Supuesto | Origen | Estado | Impacto si es falso |
|---|---|---|---|---|
| S1 | Azul habla y entiende español | Fase 0 | Confirmado | Cambian las voces y los modelos de voz |
| S2 | El equipo principal es el portátil Dell con Windows 10 Home | Fase 0 | Confirmado | Cambia el entorno de la ADR 0001 |
| S3 | "Desde el celular" significa una app web, no una app de tienda | Fase 0 | Confirmado | Habría que hacer una app nativa |
| S4 | La memoria debe persistir entre conversaciones de días distintos | Fase 0 | Confirmado | Bastaría una memoria más simple |
| S5 | Se usará el plan personal gratuito de Tailscale | Fase 1 | Confirmado (cuenta creada el 2026-10-05) | Habría que buscar otra opción de acceso |
| S6 | El uso será moderado, unos 30 minutos de conversación al día | Fase 2 | Pendiente (se medirá) | El costo cambia en proporción |
| S7 | El usuario crea las cuentas de Anthropic y Deepgram y carga las claves en `.env` | Fase 2 | Pendiente | No hay pruebas reales hasta tener las claves |
| S8 | Python 3.13 instalado con `uv`, solo para Azul | Fase 3 | Confirmado (instalado el 2026-10-04) | — |
| S9 | La cuenta de Anthropic tiene acceso a las betas de esfuerzo por mensaje y de reintento ante rechazos | Incremento 1 | Confirmado (prueba real del 2026-10-05) | Se apagan en `.env` (`AZUL_ANTHROPIC_PER_MESSAGE_EFFORT=false`, `AZUL_ANTHROPIC_FALLBACKS=false`); sin la primera, cambiar el esfuerzo invalida la caché |
| S10 | Una pregunta diaria del clima cuesta ~4–8 centavos (~1,80 USD/mes) | Incremento 1 | Confirmado: 6,1 centavos medidos | Ajustar las estimaciones de costo |
| S11 | Azul empieza a responder en 2–3 s | Fase 4 (meta del MVP) | Parcial. Texto: 2–3 s con caché activa. Voz (incremento 2): ~6 s desde que el usuario se calla en preguntas simples; con búsqueda, 15–25 s, pero con frases de espera ("Dame un segundo", "Déjame buscarlo") | El usuario lo aceptó como "funciona bien"; hay mejoras de velocidad propuestas |

## Requisitos confirmados por el usuario

| # | Requisito |
|---|---|
| R1 | Azul debe poder migrarse a otro PC, a un servidor o a la nube sin perder información |
| R2 | Personalidad cercana y casual; tutea al usuario |
| R3 | Límite de gasto de 50 USD al mes, con aviso a los 40 |
