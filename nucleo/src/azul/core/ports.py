"""Puertos: los contratos que el núcleo espera de cada pieza externa.

Cada proveedor (Anthropic, Deepgram, SQLite…) se conecta mediante un adaptador
que cumple uno de estos contratos. Cambiar de proveedor es escribir otro
adaptador, sin tocar el núcleo (ADR 0008).

Son contratos iniciales: se ajustarán en los incrementos a medida que se
implemente cada pieza.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

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
class BrainRequest:
    system: str
    messages: list[Message]
    effort: Effort = Effort.MEDIUM


@dataclass(frozen=True)
class Transcript:
    text: str
    is_final: bool


@dataclass(frozen=True)
class Usage:
    """Un consumo con costo, para el control de gasto (R3)."""

    provider: str
    cost_usd: float
    detail: str = ""


class Brain(Protocol):
    """El cerebro: recibe la conversación y devuelve la respuesta por partes."""

    def respond(self, request: BrainRequest) -> AsyncIterator[str]: ...


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

    async def add_fact(self, fact: Fact) -> None: ...

    async def facts(self) -> list[Fact]: ...


class UsageMeter(Protocol):
    """El medidor de gasto mensual."""

    async def record(self, usage: Usage) -> None: ...

    async def month_total_usd(self) -> float: ...
