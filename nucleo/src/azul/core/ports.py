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
    # Lo que Azul consultó de verdad para esta respuesta ("búsqueda web; clima: …").
    consulted: str = ""


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


@dataclass(frozen=True)
class Searching:
    """El cerebro empezó a buscar en internet (para avisar y no dejar silencio)."""


# El cerebro emite trozos de texto a medida que responde, avisos y consumos con costo.
BrainEvent = str | Searching | Usage


class BrainError(Exception):
    """Fallo del cerebro, con un mensaje apto para mostrar al usuario."""


class VoiceError(Exception):
    """Fallo del oído o la voz, con un mensaje apto para mostrar al usuario."""


class WeatherError(Exception):
    """Fallo al consultar el clima, con un mensaje apto para el usuario."""


@dataclass(frozen=True)
class Transcript:
    text: str
    is_final: bool
    # El proveedor detectó que la persona dejó de hablar (silencio tras la frase).
    ends_speech: bool = False


class Brain(Protocol):
    """El cerebro: recibe la conversación y devuelve la respuesta por partes."""

    def respond(self, request: BrainRequest) -> AsyncIterator[BrainEvent]: ...

    async def prewarm(self, request: BrainRequest) -> Usage | None:
        """Prepara la caché del proveedor para que la próxima respuesta empiece antes."""
        ...


class SpeechToText(Protocol):
    """El oído: convierte audio en vivo (PCM 16 bits, mono) en texto."""

    def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Transcript | Usage]: ...


class TextToSpeech(Protocol):
    """La voz: convierte texto en audio (MP3)."""

    def synthesize(self, text: str) -> AsyncIterator[bytes | Usage]: ...


class WeatherProvider(Protocol):
    """El clima: estado actual y pronóstico de un lugar (ADR 0024)."""

    async def forecast(self, place: str, days: int) -> dict[str, Any]: ...


class RedNacionalError(Exception):
    """Fallo al hablar con el tablero de Red Nacional, con un mensaje apto para el usuario."""


class RedNacional(Protocol):
    """El tablero de Red Nacional de Confianza IPS, en el PC de Optometría (ADR 0031).

    Azul no hace el trabajo: le pide al tablero lo mismo que piden sus botones.
    """

    async def consultar(self, seccion: str, parametros: dict[str, str]) -> Any: ...

    async def ejecutar(self, operacion: str, datos: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class Habilidad:
    """Instrucciones para hacer bien un tipo de tarea (ADR 0032), en formato SKILL.md."""

    nombre: str
    descripcion: str
    instrucciones: str


class DocumentosError(Exception):
    """Fallo con un archivo, con un mensaje apto para el usuario."""


class Documentos(Protocol):
    """Los archivos del usuario en el portátil: buscar, leer, convertir y crear (ADR 0032).

    Nunca borra ni sobrescribe: lo que crea es siempre un archivo nuevo.
    """

    async def buscar(self, texto: str, extensiones: list[str]) -> list[dict[str, Any]]: ...

    async def leer(self, ruta: str) -> str: ...

    async def pdf_a_word(self, ruta: str) -> str: ...

    async def crear_word(self, titulo: str, contenido: str, modelo: str | None) -> str: ...

    async def crear_excel(self, titulo: str, hojas: list[dict[str, Any]]) -> str: ...

    async def guardar_archivo(self, nombre: str, extension: str, contenido: str) -> str: ...


class MemoryStore(Protocol):
    """La memoria: historial de conversación y datos sobre el usuario."""

    async def add_message(self, message: Message) -> None: ...

    async def recent_messages(self, limit: int) -> list[Message]: ...

    async def message_count(self) -> int: ...

    async def add_fact(self, fact: Fact) -> bool: ...

    async def facts(self) -> list[Fact]: ...


class UsageMeter(Protocol):
    """El medidor de gasto mensual."""

    async def record(self, usage: Usage) -> None: ...

    async def month_total_usd(self) -> float: ...
