# 0012. Seguridad: autonomía total con orden de parada

- Estado: Aprobada
- Fecha: 2026-10-04
- Capa: 3 (estructura interna)
- Tipo: A (difícil de revertir)

## Contexto
Hay que definir qué puede hacer Azul sin preguntar antes de que tenga acceso a correo, agenda o PC.

## Opciones consideradas
1. Siempre confirmar las acciones (era la recomendación).
2. Confirmar solo lo irreversible.
3. Autonomía total.

Protecciones complementarias que se ofrecieron:
- Una bitácora visible de acciones (**rechazada por el usuario**).
- Una orden de parada (**aceptada**).
- Un interruptor para volver a "siempre confirma" (**rechazado por el usuario**).

## Decisión
- **Autonomía total.** Azul actúa sin pedir confirmación.
- **Orden de parada por voz** ("para", "detente", "alto", "cancela" y variantes) y por **botón**. Se reconoce *antes* de consultar al cerebro, para reaccionar de inmediato; si la frase es ambigua, decide el cerebro.
- **Acceso:** solo por la red privada (ADR 0003) más una clave de acceso de la app (`AZUL_ACCESS_KEY`).
- **Secretos:** solo en `.env`, que nunca se sube al repositorio.

## Consecuencias
- Un malentendido de voz puede ejecutar una acción no deseada, sin una bitácora para revisarla. El riesgo crece al conectar correo, agenda y PC; se le recordará al usuario en esas versiones.
- Lo que ya terminó no se deshace con la orden de parada.
- Existen registros técnicos para diagnosticar fallos, sin datos sensibles. No son una función para el usuario.

## Cómo revertirla
Agregar la confirmación o la bitácora es un cambio acotado en el registro de herramientas.
