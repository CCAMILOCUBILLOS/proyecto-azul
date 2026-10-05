"""Oído y voz con Deepgram (ADR 0006).

Se usa la API directamente (WebSocket y HTTP) en lugar del SDK de Deepgram:
son dos llamadas simples y así no dependemos de los cambios de versión del SDK.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from urllib.parse import urlencode

import httpx2
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import InvalidStatus, WebSocketException

from azul.core.ports import Transcript, Usage, VoiceError

log = logging.getLogger(__name__)

STT_URL = "wss://api.deepgram.com/v1/listen"
TTS_URL = "https://api.deepgram.com/v1/speak"

# Audio que envía la app: PCM de 16 bits, mono, 16 kHz.
SAMPLE_RATE = 16_000
BYTES_PER_SECOND = SAMPLE_RATE * 2

# Precios aproximados (octubre de 2026); se usan para el control de gasto.
STT_USD_PER_MINUTE = 0.0048  # Nova-3, streaming, un idioma
TTS_USD_PER_1K_CHARS = 0.030  # Aura-2
TTS_MAX_CHARS = 2000  # límite por solicitud de Deepgram

# Silencio que marca el final de lo que dice el usuario (ADR 0011).
ENDPOINTING_MS = 1000
UTTERANCE_END_MS = 1500


class DeepgramSpeechToText:
    def __init__(self, api_key: str, *, model: str = "nova-3", language: str = "es", connect=None):
        self._api_key = api_key
        self._model = model
        self._language = language
        self._connect = connect or ws_connect

    async def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Transcript | Usage]:
        query = urlencode(
            {
                "model": self._model,
                "language": self._language,
                "encoding": "linear16",
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
                "punctuate": "true",
                "smart_format": "true",
                "interim_results": "true",
                # Sin esto, "Azul" a veces se entiende como "Suele".
                "keyterm": "Azul",
                # Detección del final: 1 s de silencio tras la frase, con respaldo a 1,5 s.
                "endpointing": ENDPOINTING_MS,
                "utterance_end_ms": UTTERANCE_END_MS,
            }
        )
        sent_bytes = 0

        try:
            async with self._connect(
                f"{STT_URL}?{query}", additional_headers={"Authorization": f"Token {self._api_key}"}
            ) as socket:

                async def send_audio() -> None:
                    nonlocal sent_bytes
                    async for chunk in audio:
                        sent_bytes += len(chunk)
                        await socket.send(chunk)
                    # Deepgram entrega lo que falte y cierra la conexión.
                    await socket.send(json.dumps({"type": "CloseStream"}))

                sender = asyncio.create_task(send_audio())
                try:
                    async for raw in socket:
                        transcript = _parse_result(raw)
                        if transcript:
                            yield transcript
                    await sender
                finally:
                    sender.cancel()
                    with suppress(asyncio.CancelledError, WebSocketException):
                        await sender
        except InvalidStatus as error:
            status = error.response.status_code
            log.error("Deepgram rechazó la conexión de voz: HTTP %s", status)
            if status in (401, 403):
                raise VoiceError(
                    "La clave de Deepgram no es válida. Revisa DEEPGRAM_API_KEY."
                ) from error
            if status == 402:
                raise VoiceError("Se acabó el saldo en Deepgram. Recarga en su consola.") from error
            raise VoiceError(
                "Deepgram rechazó la conexión. Quedó en el registro técnico."
            ) from error
        except (OSError, WebSocketException) as error:
            log.error("Error de conexión con Deepgram: %s", error)
            raise VoiceError("No pude conectarme con Deepgram para escucharte.") from error

        if sent_bytes:
            minutes = sent_bytes / BYTES_PER_SECOND / 60
            yield Usage("deepgram", minutes * STT_USD_PER_MINUTE, f"{self._model} · voz a texto")


def _parse_result(raw: str | bytes) -> Transcript | None:
    message = json.loads(raw)
    if message.get("type") == "UtteranceEnd":
        return Transcript("", is_final=True, ends_speech=True)
    if message.get("type") != "Results":
        return None
    alternatives = message.get("channel", {}).get("alternatives") or [{}]
    text = alternatives[0].get("transcript", "").strip()
    ends_speech = bool(message.get("speech_final"))
    if not text and not ends_speech:
        return None
    return Transcript(text, is_final=bool(message.get("is_final")), ends_speech=ends_speech)


class DeepgramTextToSpeech:
    def __init__(self, api_key: str, *, voice: str, client: httpx2.AsyncClient | None = None):
        self._api_key = api_key
        self._voice = voice
        self._client = client or httpx2.AsyncClient(timeout=30)

    async def synthesize(self, text: str) -> AsyncIterator[bytes | Usage]:
        if len(text) > TTS_MAX_CHARS:
            log.warning("Frase de %d caracteres recortada para la voz", len(text))
            text = text[:TTS_MAX_CHARS]
        try:
            async with self._client.stream(
                "POST",
                TTS_URL,
                params={"model": self._voice, "encoding": "mp3"},
                headers={"Authorization": f"Token {self._api_key}"},
                json={"text": text},
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    log.error("Deepgram TTS HTTP %s: %s", response.status_code, body[:300])
                    raise VoiceError(_tts_error_message(response.status_code))
                async for chunk in response.aiter_bytes():
                    yield chunk
        except httpx2.HTTPError as error:
            log.error("Error de conexión con Deepgram TTS: %s", error)
            raise VoiceError("No pude conectarme con Deepgram para hablarte.") from error

        yield Usage(
            "deepgram", len(text) / 1000 * TTS_USD_PER_1K_CHARS, f"{self._voice} · texto a voz"
        )


def _tts_error_message(status: int) -> str:
    if status in (401, 403):
        return "La clave de Deepgram no es válida. Revisa DEEPGRAM_API_KEY."
    if status == 402:
        return "Se acabó el saldo en Deepgram. Recarga en su consola."
    return "Deepgram no pudo generar la voz. Quedó en el registro técnico."


class UnconfiguredVoice:
    """Oído y voz de reemplazo mientras no haya clave de Deepgram."""

    MESSAGE = (
        "Aún no puedo escuchar ni hablar: falta la clave de Deepgram. Pégala en el archivo "
        ".env (DEEPGRAM_API_KEY=...) y reinicia Azul."
    )

    async def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Transcript | Usage]:
        raise VoiceError(self.MESSAGE)
        yield  # pragma: no cover - convierte la función en generador

    async def synthesize(self, text: str) -> AsyncIterator[bytes | Usage]:
        raise VoiceError(self.MESSAGE)
        yield  # pragma: no cover - convierte la función en generador
