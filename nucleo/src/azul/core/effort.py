"""Elige cuánto debe pensar el cerebro para cada mensaje (ADR 0014).

Por defecto, poco: en una conversación por voz, cada segundo de razonamiento se
nota como silencio. Más solo cuando el pedido lo amerita. (Antes, cualquier
mensaje largo pensaba más, y por voz casi todo es largo.)
"""

from azul.core.ports import Effort

# Pedidos explícitos de pensar a fondo.
_DEEP_HINTS = (
    "a fondo",
    "en detalle",
    "detalladamente",
    "paso a paso",
    "piensa bien",
    "analiza bien",
)

# Señales de que la pregunta pide razonar, no solo responder.
_REASONING_HINTS = (
    "por qué",
    "porqué",
    "explica",
    "explícame",
    "analiza",
    "compara",
    "planea",
    "planifica",
    "estrategia",
    "resume",
    "redacta",
    "escribe",
    "calcula",
)


def choose_effort(text: str) -> Effort:
    normalized = text.lower()
    if any(hint in normalized for hint in _DEEP_HINTS):
        return Effort.HIGH
    if any(hint in normalized for hint in _REASONING_HINTS):
        return Effort.MEDIUM
    return Effort.LOW
