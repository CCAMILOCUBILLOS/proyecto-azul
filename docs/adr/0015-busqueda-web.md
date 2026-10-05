# 0015. Búsqueda web desde el MVP

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 4 (conexiones externas)
- Tipo: B (reversible)

## Contexto
Sin acceso a internet, Azul no puede responder sobre el clima, las noticias ni otros datos actuales.

## Decisión
Usar la herramienta de búsqueda web del lado del servidor de Anthropic (`web_search`), sin cuenta adicional.

## Consecuencias
- Cuesta $10 por cada 1.000 búsquedas, más los tokens del contenido que lee. Estimado: ~3–7 USD al mes.
- El gasto entra en el control mensual (R3).

## Cómo revertirla
Quitar la herramienta del registro.
