from datetime import datetime

import pytest

from azul.adapters.sqlite_store import SqliteStore
from azul.core.conversation import BudgetNotice, Conversation, ErrorNotice, TextChunk
from azul.core.ports import Effort, Fact, Message, Usage
from tests.fakes import FakeBrain

pytestmark = pytest.mark.anyio


@pytest.fixture
def store(tmp_path):
    return SqliteStore(tmp_path / "azul.db")


def make_conversation(brain, store, budget=50.0, warning=40.0):
    return Conversation(
        brain,
        memory=store,
        meter=store,
        monthly_budget_usd=budget,
        budget_warning_usd=warning,
        now=lambda: datetime(2026, 10, 4, 18, 30),
    )


async def collect(conversation, text):
    return [event async for event in conversation.reply(text)]


async def test_streams_answer_and_saves_both_messages(store):
    brain = FakeBrain(["Hola, ", "¿qué más?", Usage("anthropic", 0.01)])
    conversation = make_conversation(brain, store)

    events = await collect(conversation, "hola")

    assert events == [TextChunk("Hola, "), TextChunk("¿qué más?")]
    assert [(m.role, m.text) for m in await store.recent_messages(10)] == [
        ("user", "hola"),
        ("assistant", "Hola, ¿qué más?"),
    ]
    assert await store.month_total_usd() == pytest.approx(0.01)


async def test_request_includes_memory_effort_and_date(store):
    await store.add_fact(Fact("Se llama Camilo."))
    await store.add_message(Message("assistant", "mensaje huérfano"))
    brain = FakeBrain(["ok"])

    await collect(make_conversation(brain, store), "¿va a llover?")

    request = brain.requests[0]
    assert "Se llama Camilo." in request.system
    assert request.effort == Effort.LOW
    assert (
        request.context == "Fecha y hora actual del usuario: domingo 4 de octubre de 2026, 18:30."
    )
    # La conversación enviada empieza siempre por el usuario.
    assert [m.text for m in request.messages] == ["¿va a llover?"]
    assert [t.name for t in request.tools] == ["remember"]


async def test_remember_tool_saves_facts_without_duplicates(store):
    brain = FakeBrain(["ok"])
    await collect(make_conversation(brain, store), "hola")
    remember = brain.requests[0].tools[0]

    assert await remember.handler({"fact": "Prefiere el café sin azúcar."}) == "Guardado."
    assert await remember.handler({"fact": "Prefiere el café sin azúcar."}) == (
        "Ya lo tenías guardado."
    )
    with pytest.raises(ValueError):
        await remember.handler({"fact": "   "})
    assert [f.text for f in await store.facts()] == ["Prefiere el café sin azúcar."]


async def test_brain_error_is_reported_and_partial_answer_saved(store):
    brain = FakeBrain(["Empecé a responder"], error="Sin conexión.")

    events = await collect(make_conversation(brain, store), "hola")

    assert events == [TextChunk("Empecé a responder"), ErrorNotice("Sin conexión.")]
    assert (await store.recent_messages(1))[0].text == "Empecé a responder"


async def test_unexpected_failure_is_reported_not_raised(store):
    class BrokenBrain:
        async def respond(self, request):
            raise RuntimeError("fallo interno")
            yield  # pragma: no cover

    events = await collect(make_conversation(BrokenBrain(), store), "hola")

    assert len(events) == 1
    assert isinstance(events[0], ErrorNotice)
    assert "registro técnico" in events[0].message


async def test_interrupted_answer_is_saved(store):
    brain = FakeBrain(["Primera parte. ", "Segunda parte."])
    replies = make_conversation(brain, store).reply("cuéntame algo")

    assert await anext(replies) == TextChunk("Primera parte. ")
    await replies.aclose()  # el usuario tocó "parar"

    assert (await store.recent_messages(1))[0].text == "Primera parte."


async def test_warns_when_spending_passes_warning(store):
    await store.record(Usage("anthropic", 39.99))
    brain = FakeBrain(["ok", Usage("anthropic", 0.02)])

    events = await collect(make_conversation(brain, store), "hola")

    assert events[-1] == BudgetNotice("warning", pytest.approx(40.01), 50.0)


async def test_blocks_when_budget_is_exhausted(store):
    await store.record(Usage("anthropic", 50.0))
    brain = FakeBrain(["no debería responder"])

    events = await collect(make_conversation(brain, store), "hola")

    assert events == [BudgetNotice("blocked", 50.0, 50.0)]
    assert brain.requests == []
    assert await store.recent_messages(10) == []
