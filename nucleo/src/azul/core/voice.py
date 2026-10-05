"""Conversación por voz: oído → conversación → voz, frase por frase (ADR 0004, 0011)."""

import asyncio
import itertools
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass

from azul.core.conversation import Conversation, ErrorNotice, ReplyEvent, SearchNotice, TextChunk
from azul.core.ports import SpeechToText, TextToSpeech, Usage, UsageMeter, VoiceError
from azul.core.sentences import SentenceSplitter
from azul.core.stop import is_stop_command

log = logging.getLogger(__name__)

SEARCH_PHRASE = "Déjame buscarlo."
# Frases cortas si Azul tarda en empezar a responder.
FILLER_SECONDS = 2.5
FILLER_PHRASES = ("Dame un segundo.", "Mmm, déjame ver.", "Ya te digo.")
# Cuánto esperar al precalentamiento antes de preguntarle al cerebro.
PREWARM_WAIT_SECONDS = 3.0
# Escucha: se corta si no se oye nada en 8 s, o tras 60 s hablando.
NO_SPEECH_SECONDS = 8.0
MAX_LISTEN_SECONDS = 60.0


@dataclass(frozen=True)
class Heard:
    """Lo que Azul va entendiendo; is_final marca la frase completa."""

    text: str
    is_final: bool


@dataclass(frozen=True)
class Speech:
    """El audio (MP3) de una frase de la respuesta."""

    audio: bytes


@dataclass(frozen=True)
class Stopped:
    """El usuario dio la orden de parada."""


@dataclass(frozen=True)
class NothingHeard:
    """No se entendió nada en el audio."""


@dataclass(frozen=True)
class ListeningEnded:
    """Azul dejó de escuchar: la app puede apagar el micrófono."""


VoiceEvent = Heard | Speech | Stopped | NothingHeard | ListeningEnded | ReplyEvent

_DONE = object()


async def _until(source: AsyncIterator[bytes], stop: asyncio.Event) -> AsyncIterator[bytes]:
    """Entrega el audio hasta que se marque stop, aunque la app siga enviando."""
    chunks = aiter(source)
    while not stop.is_set():
        next_chunk = asyncio.ensure_future(anext(chunks))
        stopped = asyncio.ensure_future(stop.wait())
        done, _ = await asyncio.wait({next_chunk, stopped}, return_when=asyncio.FIRST_COMPLETED)
        stopped.cancel()
        if next_chunk not in done:
            next_chunk.cancel()
            return
        try:
            chunk = next_chunk.result()
        except StopAsyncIteration:
            return
        yield chunk


class VoiceSession:
    def __init__(
        self,
        conversation: Conversation,
        stt: SpeechToText,
        tts: TextToSpeech,
        meter: UsageMeter,
        *,
        filler_seconds: float = FILLER_SECONDS,
        no_speech_seconds: float = NO_SPEECH_SECONDS,
        max_listen_seconds: float = MAX_LISTEN_SECONDS,
    ) -> None:
        self._conversation = conversation
        self._stt = stt
        self._tts = tts
        self._meter = meter
        self._filler_seconds = filler_seconds
        self._no_speech_seconds = no_speech_seconds
        self._max_listen_seconds = max_listen_seconds
        self._fillers = itertools.cycle(FILLER_PHRASES)
        self._background: set[asyncio.Task[None]] = set()

    async def handle(self, audio: AsyncIterator[bytes]) -> AsyncIterator[VoiceEvent]:
        """Procesa una intervención: desde que se toca el micrófono hasta la respuesta."""
        # Mientras el usuario habla, la caché del cerebro se va preparando.
        prewarm = self._start_background(self._prewarm())

        stop_listening = asyncio.Event()
        heard_something = asyncio.Event()
        timer = asyncio.create_task(self._listening_timer(stop_listening, heard_something))
        announced_end = False
        finals: list[str] = []
        try:
            async with aclosing(self._stt.transcribe(_until(audio, stop_listening))) as transcripts:
                async for item in transcripts:
                    if isinstance(item, Usage):
                        await self._meter.record(item)
                        continue
                    if item.text:
                        heard_something.set()
                        if item.is_final:
                            finals.append(item.text)
                            yield Heard(" ".join(finals), is_final=False)
                        else:
                            yield Heard(" ".join([*finals, item.text]), is_final=False)
                    if item.ends_speech and finals and not announced_end:
                        # El usuario dejó de hablar: se deja de escuchar y se responde.
                        stop_listening.set()
                        announced_end = True
                        yield ListeningEnded()
        except VoiceError as error:
            yield ErrorNotice(str(error))
            return
        finally:
            timer.cancel()

        if not announced_end:
            yield ListeningEnded()
        text = " ".join(finals).strip()
        if not text:
            yield NothingHeard()
            return
        yield Heard(text, is_final=True)
        if is_stop_command(text):
            yield Stopped()
            return

        await asyncio.wait({prewarm}, timeout=PREWARM_WAIT_SECONDS)
        # aclosing: si el usuario interrumpe, la respuesta se corta y se guarda en el acto.
        async with aclosing(self._reply(text)) as events:
            async for event in events:
                yield event

    async def _reply(self, text: str) -> AsyncIterator[VoiceEvent]:
        out: asyncio.Queue[object] = asyncio.Queue()
        sentences: asyncio.Queue[str | None] = asyncio.Queue()
        has_spoken = asyncio.Event()

        async def say(sentence: str) -> None:
            has_spoken.set()
            await sentences.put(sentence)

        async def produce_text() -> None:
            splitter = SentenceSplitter()
            try:
                async with aclosing(self._conversation.reply(text)) as events:
                    async for event in events:
                        await out.put(event)
                        if isinstance(event, TextChunk):
                            for sentence in splitter.feed(event.text):
                                await say(sentence)
                        elif isinstance(event, SearchNotice):
                            await say(SEARCH_PHRASE)
                rest = splitter.flush()
                if rest:
                    await say(rest)
            finally:
                await sentences.put(None)

        async def fill_silence() -> None:
            # Si Azul tarda en empezar, dice algo corto para que no parezca colgado.
            try:
                await asyncio.wait_for(has_spoken.wait(), self._filler_seconds)
            except TimeoutError:
                await say(next(self._fillers))

        async def produce_audio() -> None:
            can_speak = True
            while (sentence := await sentences.get()) is not None:
                if can_speak:
                    try:
                        await out.put(Speech(await self._synthesize(sentence)))
                    except VoiceError as error:
                        # Sin voz, la respuesta sigue llegando como texto.
                        can_speak = False
                        await out.put(ErrorNotice(str(error)))
            await out.put(_DONE)

        tasks = [
            asyncio.create_task(produce_text()),
            asyncio.create_task(produce_audio()),
            asyncio.create_task(fill_silence()),
        ]
        try:
            while (event := await out.get()) is not _DONE:
                yield event  # type: ignore[misc]
        finally:
            # Si el usuario interrumpe, se detienen el cerebro y la voz.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _synthesize(self, sentence: str) -> bytes:
        audio = bytearray()
        async with aclosing(self._tts.synthesize(sentence)) as chunks:
            async for chunk in chunks:
                if isinstance(chunk, Usage):
                    await self._meter.record(chunk)
                else:
                    audio.extend(chunk)
        return bytes(audio)

    async def _listening_timer(self, stop: asyncio.Event, heard: asyncio.Event) -> None:
        """Deja de escuchar si el usuario no dice nada, o si habla demasiado tiempo."""
        try:
            await asyncio.wait_for(heard.wait(), self._no_speech_seconds)
        except TimeoutError:
            stop.set()
            return
        await asyncio.sleep(max(0.0, self._max_listen_seconds - self._no_speech_seconds))
        stop.set()

    async def _prewarm(self) -> None:
        try:
            await self._conversation.prewarm()
        except Exception:
            log.exception("Falló el precalentamiento de la caché")

    def _start_background(self, coroutine) -> asyncio.Task[None]:
        # Se guarda la referencia para que la tarea termine aunque el usuario interrumpa.
        task = asyncio.create_task(coroutine)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task
