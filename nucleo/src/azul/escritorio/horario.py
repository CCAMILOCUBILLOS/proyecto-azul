"""Horario en que "Oye Azul" escucha en el portátil (ADR 0028)."""

from datetime import time


def parse_hora(texto: str) -> time:
    """'7:00' o '07:00' → time(7, 0)."""
    horas, _, minutos = texto.strip().partition(":")
    return time(int(horas), int(minutos or 0))


def dentro_del_horario(ahora: time, desde: time, hasta: time) -> bool:
    """Admite horarios que cruzan la medianoche (p. ej. 22:00–02:00)."""
    if desde <= hasta:
        return desde <= ahora < hasta
    return ahora >= desde or ahora < hasta
