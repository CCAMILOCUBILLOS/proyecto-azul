# 0024. Clima con Open-Meteo

- Estado: Aprobada por el usuario el 2026-10-05 (mejora de velocidad B)
- Fecha: 2026-10-05
- Capa: 4 (conexiones externas)
- Tipo: B (reversible)

## Contexto
Las preguntas del clima pasaban por la búsqueda web: 10 a 15 s y unos 6 ¢ cada una.

## Decisión
Una herramienta `clima(lugar, dias)` detrás del puerto `WeatherProvider`, con el adaptador `OpenMeteoWeather`:
- Geocodificación (`geocoding-api.open-meteo.com`) para ubicar el lugar. Si viene "Ciudad, País", se prefiere el resultado que coincide con el país o la región.
- Pronóstico (`api.open-meteo.com`): el estado actual y de 1 a 7 días, con las descripciones en español de los códigos de la OMM.
- Sin cuenta, sin clave y gratuito para uso personal no comercial.
- La personalidad indica usar `clima` en vez de la búsqueda web para el clima.

## Consecuencias
- Prueba real del 2026-10-05: "¿Qué clima hace hoy?" respondió en **6,3 s** (antes, de 15 a 25 s), con datos de Villavicencio tomados de la memoria.
- La búsqueda web queda para noticias, precios y otros datos actuales.
- Se suma una dependencia externa (Open-Meteo). Si falla, Azul lo dice y puede recurrir a la búsqueda web.

## Cómo revertirla
Quitar el adaptador al crear `Conversation`; Azul vuelve a usar la búsqueda web.
