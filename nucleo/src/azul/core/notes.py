"""Notas de memoria dentro de la respuesta (ADR 0023).

Azul anota lo que aprende escribiendo <recordar>…</recordar> en su propia
respuesta, en vez de usar una herramienta aparte; así no hace falta una segunda
vuelta al cerebro. Este filtro quita las notas del texto mientras llega por
partes, para que el usuario no las vea ni las escuche.
"""

OPEN = "<recordar>"
CLOSE = "</recordar>"


class FactNotes:
    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False

    def feed(self, text: str) -> tuple[str, list[str]]:
        """Devuelve el texto visible y las notas completas encontradas hasta ahora."""
        self._buffer += text
        visible: list[str] = []
        facts: list[str] = []
        while True:
            if not self._inside:
                start = self._buffer.find(OPEN)
                if start == -1:
                    # Si el texto termina en un posible inicio de nota ("<rec"), se espera; y
                    # los espacios finales también, por si después viene una nota.
                    held = _partial_tag_length(self._buffer, OPEN)
                    text = self._buffer[: len(self._buffer) - held]
                    shown = text.rstrip()
                    visible.append(shown)
                    self._buffer = self._buffer[len(shown) :]
                    break
                # Los espacios y saltos de línea justo antes de una nota sobran.
                visible.append(self._buffer[:start].rstrip())
                self._buffer = self._buffer[start + len(OPEN) :]
                self._inside = True
            else:
                end = self._buffer.find(CLOSE)
                if end == -1:
                    break
                fact = self._buffer[:end].strip()
                if fact:
                    facts.append(fact)
                self._buffer = self._buffer[end + len(CLOSE) :]
                self._inside = False
        return "".join(visible), facts

    def flush(self) -> str:
        """Texto pendiente al terminar. Una nota sin cerrar se descarta."""
        rest = "" if self._inside else self._buffer.rstrip()
        self._buffer, self._inside = "", False
        return rest


def _partial_tag_length(text: str, tag: str) -> int:
    for length in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:length]):
            return length
    return 0
