"""Frase de activación "Oye Azul" (ADR 0011, ADR 0025).

Solo cuenta si la frase *empieza* llamando a Azul; así "el cielo es azul" o una
conversación ajena no lo despiertan.
"""

import re
import unicodedata

# Deepgram no siempre escribe "Oye": a veces entiende "hoy", "oy", "hey", "ey" u
# "o", o se come la palabra. Por eso se acepta:
#   - una palabra de llamada seguida de "azul" ("oye azul", "hoy, azul", "okey azul"), o
#   - "Azul" solo al inicio, si es un llamado: seguido de coma, pregunta o exclamación
#     ("Azul, ¿qué hora es?"), pero no "Azul es mi color favorito".
_PREFIX = r"^[\s¡¿\"']*"
_CALL = r"(?:oye|oyes|oy|hoy|oiga|hey|ey|o|ok|okey|okay)"
_WITH_CALL = re.compile(_PREFIX + _CALL + r"[\s,]+azul\b[\s,.:;!?]*", re.IGNORECASE)
_VOCATIVE = re.compile(_PREFIX + r"azul\s*(?:[,.:;!?]+[\s,.:;!?]*|$)", re.IGNORECASE)


def split_wake_phrase(text: str) -> str | None:
    """Lo que viene después del llamado a Azul ("" si no dijo nada más), o None si
    la frase no empieza llamando a Azul."""
    plain = _without_accents(text)
    match = _WITH_CALL.match(plain) or _VOCATIVE.match(plain)
    if not match:
        return None
    # La versión sin tildes tiene la misma longitud, así que la posición sirve
    # para cortar el texto original.
    return text[match.end() :].strip()


def _without_accents(text: str) -> str:
    return "".join(unicodedata.normalize("NFD", char)[0] for char in text)
