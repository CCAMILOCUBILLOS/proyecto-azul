"""Divide la respuesta en frases a medida que llega, para empezar a hablar antes."""

import re

# Fin de frase: . ! ? … seguido de un espacio o salto de línea.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


class SentenceSplitter:
    def __init__(self) -> None:
        self._pending = ""

    def feed(self, text: str) -> list[str]:
        """Agrega texto y devuelve las frases que ya quedaron completas."""
        self._pending += text
        parts = _SENTENCE_END.split(self._pending)
        self._pending = parts.pop()
        return [part.strip() for part in parts if part.strip()]

    def flush(self) -> str | None:
        """Devuelve lo que quede al terminar la respuesta."""
        rest, self._pending = self._pending.strip(), ""
        return rest or None
