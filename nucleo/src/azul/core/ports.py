"""Puertos: los contratos que el núcleo espera de cada pieza externa.

Cada proveedor (Anthropic, Deepgram, SQLite…) se conecta mediante un adaptador
que cumple uno de estos contratos. Cambiar de proveedor es escribir otro
adaptador, sin tocar el núcleo (ADR 0008).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant"]


class Effort(StrEnum):
    """Cuánto debe pensar el cerebro (ADR 0014)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Message:
    role: Role
    text: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class Fact:
    """Un dato importante sobre el usuario que Azul recuerda."""

    text: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class Usage:
    """Un consumo con costo, para el control de gasto (R3)."""

    provider: str
    cost_usd: float
    detail: str = ""


@dataclass(frozen=True)
class ToolSpec:
    """Una herramienta que el cerebro puede usar; el núcleo la ejecuta."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class BrainRequest:
    system: str
    messages: list[Message]
    effort: Effort = Effort.MEDIUM
    # Información volátil (fecha y hora) que va al final para no romper la caché.
    context: str | None = None
    tools: list[ToolSpec] = field(default_factory=list)


# El cerebro emite trozos de texto a medida que responde, y consumos con costo.
BrainEvent = str | Usage


class BrainError(Exception):
    """Fallo del cerebro, con un mensaje apto para mostrar al usuario."""


@dataclass(frozen=True)
class Transcript:
    text: str
    is_final: bool


class Brain(Protocol):
    """El cerebro: recibe la conversación y devuelve la respuesta por partes."""

    def respond(self, request: BrainRequest) -> AsyncIterator[BrainEvent]: ...


class SpeechToText(Protocol):
    """El oído: convierte audio en vivo en texto."""

    def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Transcript]: ...


class TextToSpeech(Protocol):
    """La voz: convierte texto en audio."""

    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...


class MemoryStore(Protocol):
    """La memoria: historial de conversación y datos sobre el usuario."""

    async def add_message(self, message: Message) -> None: ...

    async def recent_messages(self, limit: int) -> list[Message]: ...

    async def add_fact(self, fact: Fact) -> bool: ...

    async def facts(self) -> list[Fact]: ...


class UsageMeter(Protocol):
    """El medidor de gasto mensual."""

    async def record(self, usage: Usage) -> None: ...

    async def month_total_usd(self) -> float: ...
