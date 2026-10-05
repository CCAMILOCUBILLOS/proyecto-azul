"""Reconoce la orden de parada por voz (ADR 0012).

Se evalúa antes de consultar al cerebro, para reaccionar de inmediato. Solo
cuenta si la frase completa es una orden corta ("Azul, para", "detente, por
favor"); una frase más larga ("para eso mejor…") la decide el cerebro.
"""

import re
import unicodedata

_STOP_WORDS = frozenset(
    {
        "para",
        "parar",
        "parale",
        "detente",
        "detenete",
        "alto",
        "cancela",
        "cancelar",
        "basta",
        "callate",
        "silencio",
        "stop",
        "suficiente",
        "espera",
        # Despedidas: también terminan el modo conversación (ADR 0026).
        "adios",
        "chao",
        "chau",
    }
)
# Frases completas de cierre.
_STOP_PHRASES = frozenset(
    {
        "eso es todo",
        "eso seria todo",
        "nada mas",
        "hasta luego",
        "hasta manana",
        "nos vemos",
    }
)
# Palabras que pueden acompañar la orden sin cambiar su sentido.
_FILLER_WORDS = frozenset(
    {"azul", "ya", "por", "favor", "oye", "ok", "vale", "bueno", "ahi", "gracias", "listo"}
)
_MAX_WORDS = 5


def is_stop_command(text: str) -> bool:
    words = _normalize(text).split()
    if not words or len(words) > _MAX_WORDS:
        return False
    # "Gracias, eso es todo": se quitan las palabras de relleno y se compara la frase.
    core = " ".join(word for word in words if word not in _FILLER_WORDS)
    if core in _STOP_PHRASES:
        return True
    has_stop = any(word in _STOP_WORDS for word in words)
    only_known = all(word in _STOP_WORDS or word in _FILLER_WORDS for word in words)
    return has_stop and only_known


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^a-z\s]", " ", without_accents)
