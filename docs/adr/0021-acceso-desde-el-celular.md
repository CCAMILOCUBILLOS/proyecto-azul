# 0021. Acceso desde el celular: Tailscale Serve y clave de la app

- Estado: Aprobada (implementa la ADR 0003 y el acceso de la ADR 0012; los detalles técnicos son de tipo B, tomados por Claude Code)
- Fecha: 2026-10-05
- Capa: 1 y 3
- Tipo: B (reversible)

## Contexto
Azul corre en el portátil (ADR 0001) y escucha solo en `127.0.0.1`. El celular necesita llegar a él con HTTPS, porque el navegador exige una conexión segura para usar el micrófono.

## Decisión
- **Publicación:** `tailscale serve --bg 8710`, autorizado por el usuario el 2026-10-05. Azul queda en `https://dell.tailc78da3.ts.net`, **solo dentro de la red privada** (*tailnet only*), con certificado HTTPS automático. Se deshace con `tailscale serve reset`.
- **¿Quién es "local"?** Una petición es local solo si llega desde `127.0.0.1` **y** no trae las cabeceras del proxy de Tailscale (`X-Forwarded-For`, `Tailscale-User-Login`). Tailscale reenvía todo desde `127.0.0.1`, así que la dirección por sí sola no basta.
- **Clave de la app:** desde fuera del portátil, toda ruta `/api` (incluido el WebSocket de voz) exige una sesión. El usuario escribe `AZUL_ACCESS_KEY` una vez y recibe una cookie `HttpOnly`, `Secure` y `SameSite=Strict` válida por un año. La cookie contiene un HMAC de la clave, no la clave. Cada intento fallido espera 1 s.
- **Rutas abiertas:** `/api/salud`, `/api/sesion` y `/api/entrar`, más los archivos de la app, para poder mostrar la pantalla de entrada.
- **App instalable:** íconos PNG (180, 192, 512 y uno *maskable*) y metadatos para iPhone.

## Consecuencias
- Probado por el usuario en su iPhone 15: funciona.
- El portátil debe estar encendido y despierto.
- Cambiar `AZUL_ACCESS_KEY` invalida las sesiones de todos los dispositivos, que deben volver a escribir la clave.

## Cómo revertirla
`tailscale serve reset` quita la publicación; el control de acceso está en `nucleo/src/azul/access.py`.
