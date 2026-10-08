"""Conversación por voz: oído → conversación → voz, frase por frase (ADR 0004, 0011)."""

import asyncio
import itertools
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from dataclasses import dataclass

from azul.core.conversation import Conversation, ErrorNotice, ReplyEvent, SearchNotice, TextChunk
from azul.core.ports import SpeechToText, TextToSpeech, Usage, UsageMeter, VoiceError
from azul.core.sentences import SentenceSplitter
from azul.core.stop import is_stop_command
from azul.core.wake import split_wake_phrase

log = logging.getLogger(__name__)

SEARCH_PHRASE = "Déjame buscarlo."
# Frases cortas si Azul tarda en empezar a responder.
FILLER_SECONDS = 2.5
FILLER_PHRASES = ("Dame un segundo.", "Mmm, déjame ver.", "Ya te digo.")
# Cuánto esperar al precalentamiento antes de preguntarle al cerebro. Si apenas
# empezó, esperarlo retrasa más de lo que ahorra (la respuesta escribe su propia caché).
PREWARM_WAIT_SECONDS = 1.0
# Escucha: se corta si no se oye nada en 8 s, o tras 60 s hablando.
NO_SPEECH_SECONDS = 8.0
MAX_LISTEN_SECONDS = 60.0
# "Oye Azul": un fragmento sin ninguna palabra en este tiempo se corta (era ruido).
NO_WORDS_SECONDS = 3.0


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


@dataclass(frozen=True)
class NotForAzul:
    """Modo "Oye Azul": lo captado no era para Azul.

    had_words=False indica que ni siquiera tenía palabras (era ruido): la app puede
    aprender ese nivel como ruido de fondo. Si tenía palabras, no, porque entonces
    dejaría de oír al usuario hablando a ese volumen.
    """

    had_words: bool = True


@dataclass(frozen=True)
class WakeOnly:
    """Modo "Oye Azul": dijeron solo "Oye Azul", sin pedir nada todavía."""


@dataclass(frozen=True)
class OtroDispositivo:
    """Lo mismo ya lo está respondiendo otro dispositivo (p. ej. el portátil y la app
    abierta oyeron el mismo "Oye Azul"): este se retira sin responder ni gastar."""


VoiceEvent = (
    Heard
    | Speech
    | Stopped
    | NothingHeard
    | ListeningEnded
    | NotForAzul
    | WakeOnly
    | OtroDispositivo
    | ReplyEvent
)

# Dos dispositivos que oyen la misma frase empiezan a responder casi a la vez (se midió
# una diferencia de 53 ms); de otro dispositivo, nadie pregunta algo nuevo tan rápido.
SEGUNDOS_MISMA_PREGUNTA = 3.0
# Con estas palabras ya se sabe si es una orden directa (que son cortas).
PALABRAS_PARA_DECIDIR = 6


class Turnero:
    """Un solo dispositivo responde a cada pregunta: el primero que la oyó."""

    def __init__(
        self,
        ventana: float = SEGUNDOS_MISMA_PREGUNTA,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ventana = ventana
        self._reloj = reloj
        self._ultimo: tuple[object | None, float] = (None, -ventana)

    def tomar(self, origen: object | None) -> bool:
        ahora = self._reloj()
        quien, cuando = self._ultimo
        if (
            origen is not None
            and quien is not None
            and quien is not origen
            and ahora - cuando < self._ventana
        ):
            return False
        self._ultimo = (origen, ahora)
        return True


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
        no_words_seconds: float = NO_WORDS_SECONDS,
        parece_orden: Callable[[str], bool] | None = None,
    ) -> None:
        # Una orden directa no usa a Claude: precalentarlo sería gasto puro (ADR 0042).
        self._parece_orden = parece_orden or (lambda _: False)
        self._no_words_seconds = no_words_seconds
        self._conversation = conversation
        self._stt = stt
        self._tts = tts
        self._meter = meter
        self._filler_seconds = filler_seconds
        self._no_speech_seconds = no_speech_seconds
        self._max_listen_seconds = max_listen_seconds
        self._fillers = itertools.cycle(FILLER_PHRASES)
        self._background: set[asyncio.Task[None]] = set()
        # Compartido por todas las conexiones: la app, el portátil y el celular.
        self._turnero = Turnero()

    async def handle(
        self, audio: AsyncIterator[bytes], origen: object | None = None
    ) -> AsyncIterator[VoiceEvent]:
        """Procesa una intervención: desde que se toca el micrófono hasta la respuesta.

        origen: la conexión que la envía, para que un solo dispositivo responda.
        """
        # Mientras el usuario habla, la caché del cerebro se va preparando, pero solo
        # cuando ya se oyó lo bastante para saber que no es una orden directa.
        prewarm: asyncio.Task[None] | None = None

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
                        if prewarm is None and self._necesita_cerebro(
                            " ".join(finals if item.is_final else [*finals, item.text]),
                            item.is_final,
                        ):
                            prewarm = self._start_background(self._prewarm())
                    if item.ends_speech and finals and not announced_end:
                        if split_wake_phrase(" ".join(finals)) == "":
                            # Solo dijo "Oye Azul" (llamado oído en el portátil): se sigue
                            # escuchando la pregunta, con el plazo de silencio desde cero.
                            finals.clear()
                            timer.cancel()
                            heard_something = asyncio.Event()
                            timer = asyncio.create_task(
                                self._listening_timer(stop_listening, heard_something)
                            )
                            continue
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
        # "Oye Azul, ¿qué hora es?" dicho de corrido: al cerebro va solo la pregunta.
        text = split_wake_phrase(text) or text
        # Sin el contenido: solo cómo terminó el turno, para poder diagnosticar.
        log.info("Turno de voz: %s", "respondiendo" if text else "no se oyó nada")
        if not text:
            yield NothingHeard()
            return
        async with aclosing(self._answer(text, prewarm, origen)) as events:
            async for event in events:
                yield event

    async def handle_wake(
        self, audio: AsyncIterator[bytes], origen: object | None = None
    ) -> AsyncIterator[VoiceEvent]:
        """Un fragmento de voz captado en modo "Oye Azul" (ADR 0025).

        La app manda solo los fragmentos con voz y los corta al detectar silencio.
        Azul responde únicamente si el fragmento empieza con "Oye Azul"; lo demás
        (la TV, otra conversación) se descarta sin mostrarlo ni guardarlo.
        """
        prewarm: asyncio.Task[None] | None = None
        finals: list[str] = []
        # El fin de la frase lo decide Deepgram, no el detector del dispositivo: en un
        # cuarto con ruido (ventilador, TV) el detector no "oye" el silencio y el
        # fragmento se alargaba hasta 17 s antes de responder.
        stop_listening = asyncio.Event()
        heard_words = asyncio.Event()
        # Si en unos segundos no aparece ninguna palabra, era ruido (un ventilador, un
        # golpe): se corta para no seguir pagando por escucharlo.
        no_words = asyncio.create_task(
            self._cut_if_no_words(heard_words, stop_listening, self._no_words_seconds)
        )
        try:
            async with aclosing(self._stt.transcribe(_until(audio, stop_listening))) as transcripts:
                async for item in transcripts:
                    if isinstance(item, Usage):
                        await self._meter.record(item)
                        continue
                    if item.text:
                        heard_words.set()
                        heard = " ".join([*finals, item.text])
                        if item.is_final:
                            finals.append(item.text)
                        command = split_wake_phrase(heard)
                        if command is not None:
                            if prewarm is None and self._necesita_cerebro(command, item.is_final):
                                # Se prepara la caché solo cuando de verdad llaman a Azul.
                                prewarm = self._start_background(self._prewarm())
                            yield Heard(command, is_final=False)
                    if item.ends_speech and finals and not stop_listening.is_set():
                        # Terminó la frase: se deja de escuchar (y de pagar) en el acto.
                        stop_listening.set()
                        yield ListeningEnded()
        except VoiceError as error:
            yield ErrorNotice(str(error))
            return
        finally:
            no_words.cancel()

        if not heard_words.is_set() and stop_listening.is_set():
            # Lo cortó el temporizador: hay que avisar a la app que deje de enviar.
            yield ListeningEnded()
        command = split_wake_phrase(" ".join(finals))
        # Sin el contenido: lo que no era para Azul no se guarda en ninguna parte.
        log.info(
            "Fragmento de voz (modo Oye Azul): %s",
            "activación"
            if command is not None
            else "ignorado"
            if heard_words.is_set()
            else "ignorado (sin palabras)",
        )
        if command is None:
            yield NotForAzul(had_words=heard_words.is_set())
            return
        if not command:
            yield WakeOnly()
            return
        async with aclosing(self._answer(command, prewarm, origen)) as events:
            async for event in events:
                yield event

    def _necesita_cerebro(self, texto: str, final: bool) -> bool:
        """¿Vale la pena precalentar? Solo si ya se sabe que no es una orden directa:
        con una frase terminada o con 6 palabras (las órdenes son cortas)."""
        pregunta = split_wake_phrase(texto) or texto
        if not final and len(pregunta.split()) < PALABRAS_PARA_DECIDIR:
            return False
        return not self._parece_orden(pregunta)

    async def _answer(
        self, text: str, prewarm: asyncio.Task[None] | None, origen: object | None = None
    ) -> AsyncIterator[VoiceEvent]:
        if not self._turnero.tomar(origen):
            log.info("Turno de voz: ya lo responde otro dispositivo")
            yield OtroDispositivo()
            return
        yield Heard(text, is_final=True)
        if is_stop_command(text):
            yield Stopped()
            return
        if prewarm is not None:
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

    @staticmethod
    async def _cut_if_no_words(heard: asyncio.Event, stop: asyncio.Event, seconds: float) -> None:
        try:
            await asyncio.wait_for(heard.wait(), seconds)
        except TimeoutError:
            stop.set()

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
