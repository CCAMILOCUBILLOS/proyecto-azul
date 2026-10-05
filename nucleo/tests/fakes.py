"""Dobles de prueba: simulan proveedores externos sin costo (ADR 0013)."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

from azul.core.ports import (
    BrainError,
    BrainEvent,
    BrainRequest,
    Transcript,
    Usage,
    VoiceError,
)


class FakeBrain:
    """Cerebro simulado: emite un guion fijo y guarda las solicitudes recibidas."""

    def __init__(self, script: list[BrainEvent] | None = None, error: str | None = None):
        self.script = script or []
        self.error = error
        self.requests: list[BrainRequest] = []
        self.prewarms: list[BrainRequest] = []

    async def respond(self, request: BrainRequest) -> AsyncIterator[BrainEvent]:
        self.requests.append(request)
        for event in self.script:
            yield event
        if self.error:
            raise BrainError(self.error)

    async def prewarm(self, request: BrainRequest) -> Usage | None:
        self.prewarms.append(request)
        return Usage("anthropic", 0.001, "precalentamiento")


class FakeSpeechToText:
    """Oído simulado: consume todo el audio y devuelve transcripciones fijas."""

    def __init__(self, transcripts: list[Transcript] | None = None, error: str | None = None):
        self.transcripts = transcripts or []
        self.error = error
        self.received: list[bytes] = []

    async def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Transcript | Usage]:
        if self.error:
            raise VoiceError(self.error)
        async for chunk in audio:
            self.received.append(chunk)
        for transcript in self.transcripts:
            yield transcript
        yield Usage("deepgram", 0.0001, "voz a texto")


class FakeTextToSpeech:
    """Voz simulada: el "audio" de cada frase es la frase en bytes."""

    def __init__(self, error: str | None = None):
        self.error = error
        self.sentences: list[str] = []

    async def synthesize(self, text: str) -> AsyncIterator[bytes | Usage]:
        if self.error:
            raise VoiceError(self.error)
        self.sentences.append(text)
        yield f"<{text}>".encode()
        yield Usage("deepgram", 0.0002, "texto a voz")


# --- Cliente de Anthropic simulado ---


def usage(input_tokens=1000, output_tokens=100, cache_write=0, cache_read=0, searches=0):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_write,
        cache_read_input_tokens=cache_read,
        server_tool_use=SimpleNamespace(web_search_requests=searches) if searches else None,
    )


def final_message(stop_reason="end_turn", content=None, model="claude-opus-5-5", **usage_kw):
    return SimpleNamespace(
        model=model, stop_reason=stop_reason, content=content or [], usage=usage(**usage_kw)
    )


def tool_use(name: str, tool_input: Any, block_id: str = "toolu_1"):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


def text_event(text: str):
    return SimpleNamespace(type="text", text=text)


def search_started_event():
    return SimpleNamespace(
        type="content_block_start",
        content_block=SimpleNamespace(type="server_tool_use", name="web_search"),
    )


class _FakeStream:
    def __init__(self, events: list[Any], final: Any, error: Exception | None):
        self._events = events
        self._final = final
        self._error = error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def __aiter__(self):
        for event in self._events:
            yield event

    async def get_final_message(self):
        return self._final


class FakeAnthropicMessages:
    """Cada llamada a stream() consume una vuelta: (eventos, mensaje final) o una excepción.

    Los eventos pueden ser textos (str) u objetos de evento.
    """

    def __init__(self, rounds: list[tuple[list[Any], Any] | Exception], created: Any = None):
        self._rounds = list(rounds)
        self._created = created
        self.calls: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []

    def stream(self, **kwargs):
        # Copia de la lista: el cerebro la sigue ampliando después de llamar.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        current = self._rounds.pop(0)
        if isinstance(current, Exception):
            return _FakeStream([], None, current)
        events, final = current
        events = [text_event(e) if isinstance(e, str) else e for e in events]
        return _FakeStream(events, final, None)

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if isinstance(self._created, Exception):
            raise self._created
        return self._created or final_message("max_tokens", cache_write=3000, output_tokens=0)


def fake_anthropic_client(rounds, created=None) -> Any:
    messages = FakeAnthropicMessages(rounds, created)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))
