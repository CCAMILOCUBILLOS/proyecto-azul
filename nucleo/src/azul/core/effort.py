"""Elige cuánto debe pensar el cerebro para cada mensaje (ADR 0014).

Regla simple a propósito: se medirá con uso real antes de refinarla.
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

# Señales de que la pregunta pide razonar, no solo charlar.
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

_SHORT_MESSAGE_WORDS = 12


def choose_effort(text: str) -> Effort:
    normalized = text.lower()
    if any(hint in normalized for hint in _DEEP_HINTS):
        return Effort.HIGH
    if any(hint in normalized for hint in _REASONING_HINTS):
        return Effort.MEDIUM
    if len(normalized.split()) <= _SHORT_MESSAGE_WORDS:
        return Effort.LOW
    return Effort.MEDIUM
