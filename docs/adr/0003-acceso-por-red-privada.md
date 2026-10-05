# 0003. Acceso desde el celular por una red privada (Tailscale)

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 1 (entorno de despliegue)
- Tipo: B en lo técnico; se consultó por ser de seguridad

## Contexto
El núcleo está en el portátil (ADR 0001) y la app web necesita HTTPS para usar el micrófono (ADR 0002). El usuario quiere usar Azul también fuera de casa.

## Opciones consideradas
1. Solo la Wi-Fi de casa, con un certificado propio.
2. Red privada personal con Tailscale (plan personal gratuito).
3. Túnel público con dominio propio (por ejemplo, Cloudflare Tunnel).

## Decisión
Opción 2. El núcleo escucha **solo en el propio equipo** (`127.0.0.1`), y Tailscale lo publica con HTTPS **únicamente** hacia los dispositivos del usuario.

## Consecuencias
- Acceso desde cualquier lugar sin exponer Azul a internet.
- Hay que instalar Tailscale en el portátil y en los celulares; el usuario crea la cuenta.
- Dependencia de Tailscale para la conexión (el tráfico va cifrado).
- Pendiente de verificar en la red del usuario.

## Cómo revertirla
La capa de acceso es independiente del núcleo: se cambia por otra opción sin tocar el código de Azul.
