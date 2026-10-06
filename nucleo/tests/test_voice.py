import asyncio

import pytest

from azul.adapters.sqlite_store import SqliteStore
from azul.core.conversation import Conversation, ErrorNotice, SearchNotice, TextChunk
from azul.core.ports import Searching, Transcript, Usage
from azul.core.voice import (
    FILLER_PHRASES,
    SEARCH_PHRASE,
    Heard,
    ListeningEnded,
    NotForAzul,
    NothingHeard,
    Speech,
    Stopped,
    VoiceSession,
    WakeOnly,
)
from tests.fakes import FakeBrain, FakeSpeechToText, FakeTextToSpeech

pytestmark = pytest.mark.anyio


@pytest.fixture
def store(tmp_path):
    return SqliteStore(tmp_path / "azul.db")


def make_session(store, brain, stt, tts=None, **options):
    conversation = Conversation(
        brain, memory=store, meter=store, monthly_budget_usd=50, budget_warning_usd=40
    )
    return VoiceSession(conversation, stt, tts or FakeTextToSpeech(), meter=store, **options)


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
    assert "".join(e.text for e in events if isinstance(e, TextChunk)) == (
        "Son las seis. Buena hora para un café."
    )
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

    assert events == [ListeningEnded(), NothingHeard()]
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

    assert "".join(e.text for e in events if isinstance(e, TextChunk)) == (
        "Primera frase. Segunda frase."
    )
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


async def test_says_something_short_if_the_answer_takes_long(store):
    class ThoughtfulBrain(FakeBrain):
        async def respond(self, request):
            await asyncio.sleep(0.2)
            yield "Listo, ya lo tengo."

    tts = FakeTextToSpeech()
    stt = FakeSpeechToText([Transcript("Piensa en algo", True)])

    await collect(make_session(store, ThoughtfulBrain(), stt, tts, filler_seconds=0.05))

    assert tts.sentences[0] in FILLER_PHRASES
    assert tts.sentences[1:] == ["Listo, ya lo tengo."]


async def test_no_filler_when_the_answer_is_quick(store):
    tts = FakeTextToSpeech()
    stt = FakeSpeechToText([Transcript("Hola", True)])

    await collect(make_session(store, FakeBrain(["¡Hola!"]), stt, tts, filler_seconds=0.5))

    assert tts.sentences == ["¡Hola!"]


async def endless_audio():
    """La app sigue enviando audio hasta que Azul diga que dejó de escuchar."""
    while True:
        yield b"pcm"
        await asyncio.sleep(0.01)


class StreamingSpeechToText:
    """Oído simulado que transcribe mientras llega el audio, como Deepgram."""

    def __init__(self, script):
        self.script = list(script)
        self.chunks = 0

    async def transcribe(self, audio):
        async for _chunk in audio:
            self.chunks += 1
            if self.script:
                yield self.script.pop(0)
        yield Usage("deepgram", 0.0001, "voz a texto")


async def test_stops_listening_when_the_user_stops_talking(store):
    stt = StreamingSpeechToText(
        [
            Transcript("¿Qué hora", False),
            Transcript("¿Qué hora es?", True),
            Transcript("", True, ends_speech=True),
        ]
    )
    brain = FakeBrain(["Son las seis."])
    session = make_session(store, brain, stt)

    events = [event async for event in session.handle(endless_audio())]

    assert events.index(ListeningEnded()) < events.index(Heard("¿Qué hora es?", is_final=True))
    assert brain.requests[0].messages[-1].text == "¿Qué hora es?"
    assert await store.month_total_usd() > 0  # el costo del oído se registró


async def test_stops_listening_if_nothing_is_said(store):
    stt = StreamingSpeechToText([])
    session = make_session(store, FakeBrain(), stt, no_speech_seconds=0.05)

    events = [event async for event in session.handle(endless_audio())]

    assert events == [ListeningEnded(), NothingHeard()]


async def test_ends_speech_before_any_words_keeps_listening(store):
    stt = StreamingSpeechToText(
        [Transcript("", True, ends_speech=True), Transcript("Hola", True, ends_speech=True)]
    )
    brain = FakeBrain(["¡Hola!"])

    events = [event async for event in make_session(store, brain, stt).handle(endless_audio())]

    assert Heard("Hola", is_final=True) in events
    assert events.count(ListeningEnded()) == 1


async def wake(session, *transcripts):
    stt = session._stt
    stt.transcripts = list(transcripts)
    return [event async for event in session.handle_wake(audio(b"pcm"))]


async def test_wake_mode_ignores_speech_not_addressed_to_azul(store):
    brain = FakeBrain(["no debería responder"])
    session = make_session(store, brain, FakeSpeechToText())

    events = await wake(session, Transcript("y entonces le dije que el carro azul", True))

    assert events == [NotForAzul()]
    assert brain.requests == []
    assert brain.prewarms == []  # no se gasta en preparar la caché por una conversación ajena
    assert await store.recent_messages(10) == []  # no se guarda nada de lo ajeno


async def test_wake_phrase_alone_asks_the_app_to_listen(store):
    brain = FakeBrain()
    session = make_session(store, brain, FakeSpeechToText())

    events = await wake(session, Transcript("Oye Azul.", True))

    assert events == [Heard("", is_final=False), WakeOnly()]
    assert brain.requests == []


async def test_wake_phrase_with_a_request_is_answered(store):
    brain = FakeBrain(["Hoy hace sol."])
    tts = FakeTextToSpeech()
    session = make_session(store, brain, FakeSpeechToText(), tts)

    events = await wake(
        session,
        Transcript("Oye Azul, ¿qué", False),
        Transcript("Oye Azul, ¿qué clima hace?", True),
    )

    assert Heard("¿qué clima hace?", is_final=True) in events
    assert brain.requests[0].messages[-1].text == "¿qué clima hace?"  # sin "Oye Azul"
    assert tts.sentences == ["Hoy hace sol."]
    assert len(brain.prewarms) == 1


async def test_wake_phrase_with_stop_command(store):
    brain = FakeBrain(["no"])
    session = make_session(store, brain, FakeSpeechToText())

    events = await wake(session, Transcript("Oye Azul, para.", True))

    assert events[-1] == Stopped()
    assert brain.requests == []


async def test_wake_fragment_ends_when_deepgram_detects_the_end_of_the_sentence(store):
    # La app sigue mandando audio (ruido de un ventilador): Azul no espera al detector.
    stt = StreamingSpeechToText(
        [
            Transcript("Oye Azul, ¿qué hora es?", True),
            Transcript("", True, ends_speech=True),
        ]
    )
    brain = FakeBrain(["Son las cuatro."])
    session = make_session(store, brain, stt)

    events = [event async for event in session.handle_wake(endless_audio())]

    assert ListeningEnded() in events
    assert events.index(ListeningEnded()) < events.index(Heard("¿qué hora es?", is_final=True))
    assert brain.requests[0].messages[-1].text == "¿qué hora es?"
    assert stt.chunks <= 3  # dejó de leer audio apenas terminó la frase


async def test_speech_not_for_azul_is_cut_short_too(store):
    stt = StreamingSpeechToText(
        [Transcript("pásame la sal", True), Transcript("", True, ends_speech=True)]
    )
    session = make_session(store, FakeBrain(), stt)

    events = [event async for event in session.handle_wake(endless_audio())]

    assert events == [ListeningEnded(), NotForAzul()]


async def test_wake_fragment_without_words_is_cut_after_a_few_seconds(store):
    stt = StreamingSpeechToText([])  # nunca aparece una palabra (ruido)
    session = make_session(store, FakeBrain(), stt, no_words_seconds=0.05)

    events = [event async for event in session.handle_wake(endless_audio())]

    assert events == [ListeningEnded(), NotForAzul(had_words=False)]
