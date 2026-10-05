# 0002. El celular se conecta por una app web instalable (PWA)

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 1 (entorno de despliegue)
- Tipo: A (difícil de revertir)

## Contexto
El usuario tiene Android **y** iPhone, y quiere hablarle a Azul desde el celular.

## Opciones consideradas
1. App web instalable (PWA).
2. App nativa en Play Store y App Store (~99 USD/año de Apple; mucho más desarrollo).
3. Bot de Telegram con notas de voz.

## Decisión
Opción 1: una sola app web, instalable como ícono en Android, iPhone y PC.

## Consecuencias
- Un solo desarrollo para todos los dispositivos.
- El micrófono del navegador exige HTTPS (lo resuelve la ADR 0003).
- En iPhone una app web no puede escuchar en segundo plano ni con la pantalla bloqueada.

## Cómo revertirla
Una app nativa puede construirse más adelante sobre el mismo núcleo, que expone la misma API.
