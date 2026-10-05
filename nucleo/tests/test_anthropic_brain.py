from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from azul.adapters.anthropic_brain import (
    FALLBACK_BETA,
    PER_MESSAGE_EFFORT_BETA,
    REFUSAL_TEXT,
    AnthropicBrain,
    UnconfiguredBrain,
    cost_usd,
)
from azul.core.ports import BrainError, BrainRequest, Effort, Message, Searching, ToolSpec, Usage
from tests.fakes import fake_anthropic_client, final_message, tool_use, usage

pytestmark = pytest.mark.anyio


def make_request(**overrides):
    defaults = {
        "system": "Eres Azul.",
        "messages": [
            Message("user", "hola"),
            Message("assistant", "¡Hola!"),
            Message("user", "¿qué tal el clima?"),
        ],
        "effort": Effort.LOW,
        "context": "Fecha: hoy.",
    }
    return BrainRequest(**{**defaults, **overrides})


async def collect(brain, request):
    return [event async for event in brain.respond(request)]


def make_brain(rounds, **options):
    client = fake_anthropic_client(rounds)
    return AnthropicBrain(client, model="claude-opus-5-5", **options), client.beta.messages


async def test_streams_text_and_reports_cost():
    brain, api = make_brain([(["Hace ", "sol."], final_message(output_tokens=50))])

    events = await collect(brain, make_request())

    assert events[:2] == ["Hace ", "sol."]
    assert isinstance(events[2], Usage)
    assert events[2].cost_usd == pytest.approx((1000 * 4 + 50 * 20) / 1_000_000)
    assert len(api.calls) == 1


async def test_request_shape_keeps_cache_friendly_order():
    brain, api = make_brain([(["ok"], final_message())])

    await collect(brain, make_request())

    call = api.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["output_config"] == {"effort": "medium"}
    assert call["fallbacks"] == "default"
    assert set(call["betas"]) == {FALLBACK_BETA, PER_MESSAGE_EFFORT_BETA}
    assert call["tools"][0]["type"] == "web_search_20260209"
    # El esfuerzo va justo antes del último mensaje del usuario y la fecha al final.
    assert call["messages"] == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "¡Hola!"},
        {"role": "system", "content": [], "output_config": {"effort": "low"}},
        {"role": "user", "content": "¿qué tal el clima?"},
        {"role": "system", "content": "Fecha: hoy."},
    ]


async def test_beta_features_can_be_turned_off():
    brain, api = make_brain([(["ok"], final_message())], fallbacks=False, per_message_effort=False)

    await collect(brain, make_request())

    call = api.calls[0]
    assert "betas" not in call
    assert "fallbacks" not in call
    assert call["output_config"] == {"effort": "low"}
    assert all(m["role"] != "system" or m["content"] for m in call["messages"])


async def test_runs_client_tools_and_continues():
    saved = []

    async def remember(tool_input):
        saved.append(tool_input["fact"])
        return "Guardado."

    tool = ToolSpec("remember", "Guarda un dato.", {"type": "object"}, remember)
    block = tool_use("remember", {"fact": "Se llama Camilo."})
    brain, api = make_brain(
        [
            (["Anotado."], final_message("tool_use", content=[block])),
            (["¡Listo, Camilo!"], final_message()),
        ]
    )

    events = await collect(brain, make_request(tools=[tool]))

    assert saved == ["Se llama Camilo."]
    assert [e for e in events if isinstance(e, str)] == ["Anotado.", " ", "¡Listo, Camilo!"]
    assert sum(isinstance(e, Usage) for e in events) == 2
    second_call_messages = api.calls[1]["messages"]
    assert second_call_messages[-2] == {"role": "assistant", "content": [block]}
    assert second_call_messages[-1] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "Guardado."}],
    }
    assert api.calls[1]["tools"][1]["strict"] is True


async def test_invalid_tool_input_is_reported_as_error():
    async def remember(tool_input):
        raise ValueError("El dato está vacío.")

    tool = ToolSpec("remember", "Guarda un dato.", {"type": "object"}, remember)
    brain, api = make_brain(
        [
            ([], final_message("tool_use", content=[tool_use("remember", {"fact": ""})])),
            (["Perdón."], final_message()),
        ]
    )

    await collect(brain, make_request(tools=[tool]))

    result = api.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert result["content"] == "El dato está vacío."


async def test_pause_turn_continues_the_answer():
    paused = final_message("pause_turn", content=[SimpleNamespace(type="server_tool_use")])
    brain, api = make_brain([(["Buscando"], paused), (["… hace sol."], final_message())])

    events = await collect(brain, make_request())

    assert len(api.calls) == 2
    assert api.calls[1]["messages"][-1] == {"role": "assistant", "content": paused.content}
    assert "… hace sol." in events


async def test_refusal_without_text_gives_friendly_message():
    brain, _ = make_brain([([], final_message("refusal"))])

    events = await collect(brain, make_request())

    assert events[-1] == REFUSAL_TEXT


async def test_connection_error_becomes_user_friendly():
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.example"))
    brain, _ = make_brain([error])

    with pytest.raises(BrainError, match="conexión a internet"):
        await collect(brain, make_request())


async def test_unconfigured_brain_explains_missing_key():
    with pytest.raises(BrainError, match="ANTHROPIC_API_KEY"):
        await collect(UnconfiguredBrain(), make_request())


def test_cost_includes_cache_and_web_search():
    cost = cost_usd(
        "claude-opus-5-5",
        usage(input_tokens=500, output_tokens=200, cache_write=1000, cache_read=4000, searches=2),
    )

    expected = (500 * 4 + 200 * 20 + 1000 * 5 + 4000 * 0.2) / 1_000_000 + 0.02
    assert cost == pytest.approx(expected)


def test_unknown_model_is_priced_conservatively():
    known = cost_usd("claude-opus-5", usage())
    unknown = cost_usd("modelo-nuevo", usage())

    assert unknown >= known


async def test_announces_web_search():
    from tests.fakes import search_started_event

    brain, _ = make_brain([([search_started_event(), "Hace sol."], final_message())])

    events = await collect(brain, make_request())

    assert isinstance(events[0], Searching)
    assert events[1] == "Hace sol."


async def test_prewarm_writes_cache_without_generating():
    client = fake_anthropic_client([])
    brain = AnthropicBrain(client, model="claude-opus-5-5")

    usage_event = await brain.prewarm(make_request())

    call = client.beta.messages.create_calls[0]
    assert call["max_tokens"] == 0
    assert "cache_control" not in call
    assert "fallbacks" not in call
    assert call["betas"] == [PER_MESSAGE_EFFORT_BETA]
    assert call["output_config"] == {"effort": "medium"}
    # La caché se marca en el último mensaje compartido con la próxima solicitud.
    assert call["messages"][-2] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "¿qué tal el clima?", "cache_control": {"type": "ephemeral"}}
        ],
    }
    assert call["messages"][-1]["role"] == "user"
    assert usage_event.cost_usd == pytest.approx(3000 * 5 / 1_000_000 + 1000 * 4 / 1_000_000)


async def test_prewarm_failure_is_not_fatal():
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.example"))
    brain = AnthropicBrain(fake_anthropic_client([], created=error), model="claude-opus-5-5")

    assert await brain.prewarm(make_request()) is None
