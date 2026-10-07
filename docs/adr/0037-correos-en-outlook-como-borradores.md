# 0037. Correos en Outlook clásico, solo como borradores

- Estado: Aprobada (alcance "nuevos y respuestas" elegido por el usuario el 2026-10-07)
- Fecha: 2026-10-07
- Capa: 4 (conexión con el Outlook del usuario)
- Tipo: B (reversible): `AZUL_CORREO_ACTIVO=false` quita las herramientas

## Contexto
El usuario pidió que Azul le redacte correos en Outlook clásico y los deje en Borradores.
En el portátil está instalado Outlook clásico (Microsoft 365, una cuenta Exchange en modo
caché). Azul ya maneja Word por PowerShell + COM para convertir PDF (ADR 0032).

## Opciones consideradas
1. **Manejar el Outlook del portátil por COM** (PowerShell): sin cuentas ni claves nuevas,
   usa la sesión abierta; solo funciona con el portátil encendido.
2. Microsoft Graph por internet: requiere registrar una aplicación en Microsoft y darle
   permisos sobre el correo; funcionaría con el portátil apagado, pero Azul vive en él.

## Decisión (y quién la aprobó)
Opción 1, recomendada en el chat; el usuario eligió el alcance "nuevos y respuestas":
- `correo_buscar`: busca en recibidos o enviados (hasta 90 días) con el **índice de
  búsqueda de Outlook** (`ci_phrasematch`), en asunto, remitente, destinatarios y texto.
  Medido: 3 a 5 s, con o sin tildes. Sin índice, un respaldo (`like`) revisa asunto y nombres.
- `correo_leer`: un correo completo (texto hasta 15.000 caracteres y nombres de adjuntos).
- `correo_borrador` y `correo_responder`: dejan el correo en Borradores (la respuesta en el
  mismo hilo y con el original citado), con la firma de Outlook y adjuntos opcionales.
- **Nunca envía**: no hay herramienta para enviar y ningún guion llama a `Send` (hay una
  prueba que lo vigila). El usuario revisa y envía.
- Lo que dice un correo llega al cerebro marcado como información de terceros, no como
  instrucciones, y las instrucciones de Azul lo repiten (defensa contra correos que intenten
  darle órdenes).
- Los datos viajan al guion por un archivo JSON temporal, nunca dentro del comando.

## Consecuencias
- Positivas: sin costo ni credenciales nuevas; el usuario conserva el control del envío.
- Negativas: depende de que Outlook clásico esté instalado y sin ventanas esperando
  respuesta. En la prueba real, el asistente de activación de Office estaba abierto: Outlook
  dejaba buscar y leer, pero no crear correos ("Hay un cuadro de diálogo abierto").
- La primera lectura masiva tras abrir Outlook es muy lenta (154 s para 500 correos); por eso
  la búsqueda usa el índice y trae como máximo 10 resultados.
- Los correos leídos pasan por Claude (Anthropic) para entenderlos.

## Cómo revertirla
`AZUL_CORREO_ACTIVO=false` en `.env` y reiniciar Azul.
