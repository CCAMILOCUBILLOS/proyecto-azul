# Estado del proyecto

Última actualización: 2026-10-04

## Fases

| Fase | Estado |
|---|---|
| 0. Descubrimiento | ✅ Completada |
| 1. Entorno de despliegue | ✅ Completada (ADR 0001–0003) |
| 2. Modelo de IA y voz | ✅ Completada (ADR 0004–0006, 0014) |
| 3. Estructura interna | ✅ Completada (ADR 0007–0013) |
| 4. MVP y hoja de ruta | ✅ Completada (ADR 0015–0017) |
| 5. Esqueleto del repositorio | ✅ Completada (ADR 0018–0019) |
| 6. Incremento 1: cerebro + memoria + gasto | 🔄 Construido y probado con simulaciones; falta la prueba real |
| 6. Incrementos 2–4 (voz, celular, respaldo) | ⏳ Pendientes |

## Incremento 1: lo que ya funciona
- Chat de texto en la app web, con respuesta por partes y botón Parar.
- Cerebro Claude Opus 5.5 con búsqueda web y esfuerzo variable por mensaje.
- Memoria en SQLite: historial y datos del usuario (herramienta `remember`).
- Control de gasto: costo por respuesta, aviso a los 40 USD y bloqueo a los 50.
- 43 pruebas automáticas.

## Próximos pasos
- El usuario carga crédito en Anthropic, fija el límite en la consola y pega `ANTHROPIC_API_KEY` en `.env`.
- Prueba real, avisando antes del costo (menos de 10 centavos). Verificar las betas (S9).
- Cerrar el incremento 1 y pasar al incremento 2 (voz con Deepgram).
