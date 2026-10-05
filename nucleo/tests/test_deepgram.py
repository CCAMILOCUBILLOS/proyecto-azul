import asyncio
import json

import httpx2
import pytest
from websockets.exceptions import InvalidStatus

from azul.adapters.deepgram import (
    STT_USD_PER_MINUTE,
    TTS_USD_PER_1K_CHARS,
    DeepgramSpeechToText,
    DeepgramTextToSpeech,
    UnconfiguredVoice,
)
from azul.core.ports import Transcript, Usage, VoiceError

pytestmark = pytest.mark.anyio


class FakeSocket:
    """WebSocket simulado de Deepgram: responde con mensajes fijos tras recibir CloseStream."""

    def __init__(self, replies):
        self.replies = replies
        self.sent = []
        self.closed = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self._messages()

    async def _messages(self):
        # Espera a que la app termine de mandar audio, como el servicio real.
        while not any(isinstance(d, str) and "CloseStream" in d for d in self.sent):
            await asyncio.sleep(0)
        for reply in self.replies:
            yield json.dumps(reply)


def results(text, is_final):
    return {
        "type": "Results",
        "is_final": is_final,
        "channel": {"alternatives": [{"transcript": text}]},
    }


async def audio(*chunks):
    for chunk in chunks:
        yield chunk


async def test_stt_streams_audio_and_reports_transcripts_and_cost():
    socket = FakeSocket(
        [
            results("hola", False),
            results("", True),
            results("Hola, Azul.", True),
            {"type": "Metadata"},
        ]
    )
    calls = []

    def connect(url, additional_headers):
        calls.append((url, additional_headers))
        return socket

    stt = DeepgramSpeechToText("clave", connect=connect)
    one_second = b"\x00" * 32_000

    items = [item async for item in stt.transcribe(audio(one_second, one_second))]

    url, headers = calls[0]
    assert url.startswith("wss://api.deepgram.com/v1/listen?")
    for param in ("model=nova-3", "language=es", "encoding=linear16", "sample_rate=16000"):
        assert param in url
    assert headers == {"Authorization": "Token clave"}
    assert socket.sent[:2] == [one_second, one_second]
    assert json.loads(socket.sent[-1]) == {"type": "CloseStream"}
    assert items[:2] == [Transcript("hola", False), Transcript("Hola, Azul.", True)]
    assert isinstance(items[-1], Usage)
    assert items[-1].cost_usd == pytest.approx(2 / 60 * STT_USD_PER_MINUTE)


async def test_stt_invalid_key_is_user_friendly():
    def connect(url, additional_headers):
        raise InvalidStatus(httpx2_response(401))

    stt = DeepgramSpeechToText("mala", connect=connect)

    with pytest.raises(VoiceError, match="clave de Deepgram"):
        [item async for item in stt.transcribe(audio(b"x"))]


def httpx2_response(status):
    from types import SimpleNamespace

    return SimpleNamespace(status_code=status)


async def test_tts_returns_mp3_and_cost():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, content=b"ID3mp3data")

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    tts = DeepgramTextToSpeech("clave", voice="aura-2-celeste-es", client=client)

    items = [item async for item in tts.synthesize("Hola, ¿cómo estás?")]

    request = requests[0]
    assert request.url.host == "api.deepgram.com"
    assert request.url.params["model"] == "aura-2-celeste-es"
    assert request.url.params["encoding"] == "mp3"
    assert request.headers["Authorization"] == "Token clave"
    assert json.loads(request.content) == {"text": "Hola, ¿cómo estás?"}
    assert b"".join(i for i in items if isinstance(i, bytes)) == b"ID3mp3data"
    assert items[-1].cost_usd == pytest.approx(18 / 1000 * TTS_USD_PER_1K_CHARS)


async def test_tts_errors_are_user_friendly():
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(402, content=b"{}"))
    )
    tts = DeepgramTextToSpeech("clave", voice="aura-2-celeste-es", client=client)

    with pytest.raises(VoiceError, match="saldo"):
        [item async for item in tts.synthesize("Hola")]


async def test_unconfigured_voice_explains_missing_key():
    with pytest.raises(VoiceError, match="DEEPGRAM_API_KEY"):
        [item async for item in UnconfiguredVoice().synthesize("Hola")]
