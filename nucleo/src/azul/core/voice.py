"""Conversación por voz: oído → conversación → voz, frase por frase (ADR 0004, 0011)."""

import asyncio
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
# Cuánto esperar al precalentamiento antes de preguntarle al cerebro.
PREWARM_WAIT_SECONDS = 3.0


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


VoiceEvent = Heard | Speech | Stopped | NothingHeard | ReplyEvent

_DONE = object()


class VoiceSession:
    def __init__(
        self,
        conversation: Conversation,
        stt: SpeechToText,
        tts: TextToSpeech,
        meter: UsageMeter,
    ) -> None:
        self._conversation = conversation
        self._stt = stt
        self._tts = tts
        self._meter = meter
        self._background: set[asyncio.Task[None]] = set()

    async def handle(self, audio: AsyncIterator[bytes]) -> AsyncIterator[VoiceEvent]:
        """Procesa una intervención: desde que se presiona el botón hasta la respuesta."""
        # Mientras el usuario habla, la caché del cerebro se va preparando.
        prewarm = self._start_background(self._prewarm())

        finals: list[str] = []
        try:
            async with aclosing(self._stt.transcribe(audio)) as transcripts:
                async for item in transcripts:
                    if isinstance(item, Usage):
                        await self._meter.record(item)
                    elif item.is_final:
                        finals.append(item.text)
                        yield Heard(" ".join(finals), is_final=False)
                    else:
                        yield Heard(" ".join([*finals, item.text]), is_final=False)
        except VoiceError as error:
            yield ErrorNotice(str(error))
            return

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

        async def produce_text() -> None:
            splitter = SentenceSplitter()
            try:
                async with aclosing(self._conversation.reply(text)) as events:
                    async for event in events:
                        await out.put(event)
                        if isinstance(event, TextChunk):
                            for sentence in splitter.feed(event.text):
                                await sentences.put(sentence)
                        elif isinstance(event, SearchNotice):
                            await sentences.put(SEARCH_PHRASE)
                rest = splitter.flush()
                if rest:
                    await sentences.put(rest)
            finally:
                await sentences.put(None)

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

        tasks = [asyncio.create_task(produce_text()), asyncio.create_task(produce_audio())]
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
