# 0033. Abrir Azul con el toque atrás del iPhone, sin Siri

- Estado: Aprobada (elegida por el usuario el 2026-10-06)
- Fecha: 2026-10-06
- Capa: 1 (cómo se activa en el celular)
- Tipo: B (reversible)

## Contexto
El atajo de Siri no le funciona al usuario (Siri interpreta mal las frases). Apple no permite que una app (web ni nativa) escuche en segundo plano en el iPhone, así que "Oye Azul" con la pantalla apagada no es posible ahí.

## Decisión
Un atajo de iOS ("Abrir URL" → `https://dell.tailc78da3.ts.net/?conversar`) asignado al **toque atrás** (Accesibilidad → Tocar → Toque atrás → Doble toque). La app, al abrirse con `?conversar`, queda lista: **un toque en cualquier parte de la pantalla** enciende el micrófono en modo conversación (iOS exige un toque para encender el audio de una página). Siri no interviene.

## Consecuencias
- El atajo abre Azul en Safari, no en el ícono instalado (iOS no deja abrir apps web por atajo). Safari pide la clave de acceso una vez y el permiso de micrófono.
- Sirve también desde el Centro de control (iOS 18) con el mismo atajo.
- Escuchar siempre sin tocar nada queda para el portátil ("Oye Azul" local) y una futura app Android.

## Cómo revertirla
Quitar el atajo del toque atrás en el iPhone. El parámetro `?conversar` no afecta el uso normal.
