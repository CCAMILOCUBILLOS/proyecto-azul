import asyncio

import pytest

from azul.adapters.sqlite_store import SqliteStore
from azul.core.conversation import Conversation, ErrorNotice, SearchNotice, TextChunk
from azul.core.ports import Searching, Transcript, Usage
from azul.core.voice import SEARCH_PHRASE, Heard, NothingHeard, Speech, Stopped, VoiceSession
from tests.fakes import FakeBrain, FakeSpeechToText, FakeTextToSpeech

pytestmark = pytest.mark.anyio


@pytest.fixture
def store(tmp_path):
    return SqliteStore(tmp_path / "azul.db")


def make_session(store, brain, stt, tts=None):
    conversation = Conversation(
        brain, memory=store, meter=store, monthly_budget_usd=50, budget_warning_usd=40
    )
    return VoiceSession(conversation, stt, tts or FakeTextToSpeech(), meter=store)


async def audio(*chunks):
    for chunk in chunks:
        yield chunk


async def collect(session, *chunks):
    return [event async for event in session.handle(audio(*chunks))]


async def test_full_voice_turn_speaks_sentence_by_sentence(store):
    stt = FakeSpeechToText([Transcript("¿qué", False), Transcript("¿Qué hora es?", True)])
    brain = FakeBrain(["Son las seis. ", "Buena hora para", " un café.", Usage("anthropic", 0.01)])
    tts = FakeTextToSpeech()

    events = await collect(make_session(store, brain, stt, tts), b"pcm1", b"pcm2")

    assert stt.received == [b"pcm1", b"pcm2"]
    assert events[0] == Heard("¿qué", is_final=False)
    assert Heard("¿Qué hora es?", is_final=True) in events
    assert tts.sentences == ["Son las seis.", "Buena hora para un café."]
    assert [e.audio for e in events if isinstance(e, Speech)] == [
        b"<Son las seis.>",
        "<Buena hora para un café.>".encode(),
    ]
    assert [e.text for e in events if isinstance(e, TextChunk)] == [
        "Son las seis. ",
        "Buena hora para",
        " un café.",
    ]
    assert brain.requests[0].messages[-1].text == "¿Qué hora es?"


async def test_prewarms_while_the_user_speaks(store):
    brain = FakeBrain(["Hola."])
    stt = FakeSpeechToText([Transcript("Hola", True)])

    await collect(make_session(store, brain, stt))

    assert len(brain.prewarms) == 1


async def test_announces_web_search_out_loud(store):
    brain = FakeBrain([Searching(), "Hace sol."])
    tts = FakeTextToSpeech()
    stt = FakeSpeechToText([Transcript("¿Qué clima hace?", True)])

    events = await collect(make_session(store, brain, stt, tts))

    assert SearchNotice() in events
    assert tts.sentences == [SEARCH_PHRASE, "Hace sol."]


async def test_stop_command_does_not_reach_the_brain(store):
    brain = FakeBrain(["no debería responder"])
    stt = FakeSpeechToText([Transcript("Azul, para.", True)])

    events = await collect(make_session(store, brain, stt))

    assert events[-1] == Stopped()
    assert brain.requests == []


async def test_silence_reports_nothing_heard(store):
    brain = FakeBrain(["no debería responder"])

    events = await collect(make_session(store, brain, FakeSpeechToText([])))

    assert events == [NothingHeard()]
    assert brain.requests == []


async def test_listening_error_is_reported(store):
    stt = FakeSpeechToText(error="La clave de Deepgram no es válida.")

    events = await collect(make_session(store, FakeBrain(), stt))

    assert events == [ErrorNotice("La clave de Deepgram no es válida.")]


async def test_voice_failure_keeps_the_text_answer(store):
    brain = FakeBrain(["Primera frase. ", "Segunda frase."])
    stt = FakeSpeechToText([Transcript("Cuéntame algo", True)])
    tts = FakeTextToSpeech(error="Deepgram no pudo generar la voz.")

    events = await collect(make_session(store, brain, stt, tts))

    assert [e.text for e in events if isinstance(e, TextChunk)] == [
        "Primera frase. ",
        "Segunda frase.",
    ]
    assert events.count(ErrorNotice("Deepgram no pudo generar la voz.")) == 1
    assert not any(isinstance(e, Speech) for e in events)


async def test_interrupting_saves_partial_answer_and_stops_tasks(store):
    class SlowBrain(FakeBrain):
        async def respond(self, request):
            yield "Empiezo a responder. "
            await asyncio.sleep(10)
            yield "Esto nunca llega."

    stt = FakeSpeechToText([Transcript("Cuéntame una historia", True)])
    events = make_session(store, SlowBrain(), stt).handle(audio(b"pcm"))

    async for event in events:
        if isinstance(event, Speech):
            break
    await events.aclose()  # el usuario tocó el botón de nuevo

    assert (await store.recent_messages(1))[0].text == "Empiezo a responder."
