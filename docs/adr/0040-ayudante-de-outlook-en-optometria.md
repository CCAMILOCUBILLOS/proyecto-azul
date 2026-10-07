# 0040. Ayudante de Outlook en el PC de Optometría

- Estado: Aprobada por el usuario el 2026-10-07
- Fecha: 2026-10-07
- Capa: 1 (qué corre en cada equipo) y 4 (Outlook de Optometría por Tailscale)
- Tipo: B (reversible): vaciar `AZUL_CORREO_REMOTO_*` vuelve al Outlook del portátil

## Contexto
Azul vive en el portátil, pero el correo real está en el Outlook clásico del PC de
Optometría (el usuario: "el funcionamiento real siempre será en el de Optometría"). En el
portátil, Office está en modo de notificaciones (licencia por volumen sin renovar, error
0xC004F00F): lee, pero no crea borradores ni cambia categorías. Se comprobó que el mismo
método de `agendar.py` de Red Nacional también falla en el portátil: no es el código, es
el equipo.

## Opciones consideradas
1. Un ayudante pequeño en Optometría que maneja su Outlook; Azul le pide por Tailscale.
2. Mudar todo Azul a Optometría (portátil y celular como controles remotos).

## Decisión (y quién la aprobó)
Opción 1, recomendada; el usuario confirmó que Optometría está encendido 24 horas.
- Los guiones de PowerShell se separaron en `outlook_powershell.py` (solo biblioteca
  estándar, Python 3.8+): los usan Azul y el ayudante, sin duplicar código.
- `ayudante-optometria/ayudante_outlook.py`: servidor HTTP mínimo en 127.0.0.1:8767,
  publicado con `tailscale serve --bg --https=8443 http://127.0.0.1:8767`.
- Clave propia (cabecera `X-Azul-Clave`, comparación en tiempo constante), creada la
  primera vez en `ayudante-optometria/.clave` (ignorado por git). Solo acepta las acciones
  conocidas (buscar, leer, borrador, responder, categorizar) y `ping`; una a la vez.
- Los adjuntos viajan en el pedido (base64) y se recrean en una carpeta temporal que se
  borra al terminar; de cada nombre solo se usa el nombre, nunca una ruta.
- En el portátil, `AZUL_CORREO_REMOTO_URL` y `AZUL_CORREO_REMOTO_CLAVE` (las escribe
  `Conectar correo de Optometria.cmd`, que primero comprueba la conexión).
- El borrador se crea dentro de la carpeta Borradores, como en `agendar.py`.

## Consecuencias
- Positivas: el correo funciona con el Outlook que sí está activo; cambio pequeño.
- Negativas: dependen dos equipos (el portátil para Azul; Optometría para el correo).
  El ayudante debe quedar abierto (inicio automático con la carpeta de Inicio de Windows).
- Riesgo: quien tenga la clave del ayudante y acceso a la red de Tailscale puede leer
  correos y dejar borradores (nunca enviar).
- Pendiente: si Optometría tiene varias cuentas, hoy se usa la predeterminada.

## Cómo revertirla
Quitar `AZUL_CORREO_REMOTO_*` del `.env` del portátil, cerrar el ayudante y
`tailscale serve --https=8443 off` en Optometría.
