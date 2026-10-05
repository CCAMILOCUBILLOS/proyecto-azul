"""Dobles de prueba: simulan proveedores externos sin costo (ADR 0013)."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

from azul.core.ports import BrainError, BrainEvent, BrainRequest


class FakeBrain:
    """Cerebro simulado: emite un guion fijo y guarda las solicitudes recibidas."""

    def __init__(self, script: list[BrainEvent] | None = None, error: str | None = None):
        self.script = script or []
        self.error = error
        self.requests: list[BrainRequest] = []

    async def respond(self, request: BrainRequest) -> AsyncIterator[BrainEvent]:
        self.requests.append(request)
        for event in self.script:
            yield event
        if self.error:
            raise BrainError(self.error)


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


class _FakeStream:
    def __init__(self, texts: list[str], final: Any, error: Exception | None):
        self._texts = texts
        self._final = final
        self._error = error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, *exc_info):
        return False

    @property
    async def text_stream(self):
        for text in self._texts:
            yield text

    async def get_final_message(self):
        return self._final


class FakeAnthropicMessages:
    """Cada llamada a stream() consume una vuelta: (textos, mensaje final) o una excepción."""

    def __init__(self, rounds: list[tuple[list[str], Any] | Exception]):
        self._rounds = list(rounds)
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs):
        # Copia de la lista: el cerebro la sigue ampliando después de llamar.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        current = self._rounds.pop(0)
        if isinstance(current, Exception):
            return _FakeStream([], None, current)
        texts, final = current
        return _FakeStream(texts, final, None)


def fake_anthropic_client(rounds) -> Any:
    messages = FakeAnthropicMessages(rounds)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))
