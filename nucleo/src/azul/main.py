"""Punto de entrada: crea la aplicación web y arranca el servidor."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing, suppress
from typing import Any

import anthropic
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from azul import __version__
from azul.access import (
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    AccessMiddleware,
    is_authorized,
    is_local,
    key_matches,
    session_token,
)
from azul.adapters.anthropic_brain import AnthropicBrain, UnconfiguredBrain
from azul.adapters.deepgram import DeepgramSpeechToText, DeepgramTextToSpeech, UnconfiguredVoice
from azul.adapters.sqlite_store import SqliteStore
from azul.backup import backup_if_due
from azul.config import Settings, get_settings
from azul.core.conversation import (
    BudgetNotice,
    Conversation,
    ErrorNotice,
    ReplyEvent,
    SearchNotice,
    TextChunk,
)
from azul.core.ports import Brain, SpeechToText, TextToSpeech
from azul.core.voice import (
    Heard,
    ListeningEnded,
    NothingHeard,
    Speech,
    Stopped,
    VoiceEvent,
    VoiceSession,
)

log = logging.getLogger(__name__)

MAX_INPUT_CHARS = 4000


class ChatInput(BaseModel):
    texto: str = Field(min_length=1, max_length=MAX_INPUT_CHARS, pattern=r"\S")


class AccessInput(BaseModel):
    clave: str = Field(min_length=1, max_length=200)


def build_brain(settings: Settings) -> Brain:
    if settings.anthropic_api_key is None:
        return UnconfiguredBrain()
    return AnthropicBrain(
        anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value()),
        model=settings.brain_model,
        fallbacks=settings.anthropic_fallbacks,
        per_message_effort=settings.anthropic_per_message_effort,
        web_search_max_uses=settings.web_search_max_uses,
    )


def build_voice(settings: Settings) -> tuple[SpeechToText, TextToSpeech]:
    if settings.deepgram_api_key is None:
        unconfigured = UnconfiguredVoice()
        return unconfigured, unconfigured
    key = settings.deepgram_api_key.get_secret_value()
    return (
        DeepgramSpeechToText(key, model=settings.stt_model, language=settings.stt_language),
        DeepgramTextToSpeech(key, voice=settings.tts_voice),
    )


def create_app(
    settings: Settings | None = None,
    *,
    brain: Brain | None = None,
    stt: SpeechToText | None = None,
    tts: TextToSpeech | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    store = SqliteStore(settings.data_dir / "azul.db")
    conversation = Conversation(
        brain or build_brain(settings),
        memory=store,
        meter=store,
        monthly_budget_usd=settings.monthly_budget_usd,
        budget_warning_usd=settings.budget_warning_usd,
    )
    if stt is None or tts is None:
        default_stt, default_tts = build_voice(settings)
        stt, tts = stt or default_stt, tts or default_tts
    voice = VoiceSession(conversation, stt, tts, meter=store)
    app = FastAPI(title="Azul", version=__version__)

    access_key = settings.access_key.get_secret_value() if settings.access_key else None
    app.add_middleware(AccessMiddleware, access_key=access_key)

    @app.get("/api/salud")
    async def salud() -> dict[str, str]:
        return {"estado": "ok", "version": __version__}

    @app.get("/api/sesion")
    async def sesion(request: Request) -> dict[str, bool]:
        return {
            "local": is_local(request.scope),
            "autorizado": is_authorized(request.scope, access_key),
            "clave_configurada": access_key is not None,
        }

    @app.post("/api/entrar", status_code=204)
    async def entrar(entrada: AccessInput, request: Request, response: Response) -> None:
        if access_key is None:
            raise HTTPException(
                503, "Azul no tiene clave de acceso: configúrala en .env (AZUL_ACCESS_KEY)."
            )
        if not key_matches(entrada.clave, access_key):
            await asyncio.sleep(1)  # frena a quien intente adivinar la clave
            raise HTTPException(401, "Clave incorrecta.")
        response.set_cookie(
            COOKIE_NAME,
            session_token(access_key),
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="strict",
            secure=not is_local(request.scope),
        )

    @app.post("/api/chat")
    async def chat(entrada: ChatInput) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            async for event in conversation.reply(entrada.texto.strip()):
                yield _ndjson(_event_to_dict(event))
            yield _ndjson({"tipo": "fin"})

        return StreamingResponse(events(), media_type="application/x-ndjson")

    @app.post("/api/precalentar", status_code=204)
    async def precalentar() -> None:
        # La app lo llama al empezar a escribir; solo actúa si la caché venció.
        await conversation.prewarm()

    @app.get("/api/gasto")
    async def gasto() -> dict[str, float]:
        return {
            "gastado_mes": round(await store.month_total_usd(), 4),
            "limite": settings.monthly_budget_usd,
            "aviso": settings.budget_warning_usd,
        }

    @app.get("/api/historial")
    async def historial(limite: int = Query(default=50, ge=1, le=200)) -> list[dict[str, str]]:
        return [
            {
                "rol": message.role,
                "texto": message.text,
                "fecha": message.created_at.isoformat() if message.created_at else "",
            }
            for message in await store.recent_messages(limite)
        ]

    @app.websocket("/api/voz")
    async def voz(socket: WebSocket) -> None:
        await _voice_connection(socket, voice)

    # La app web compilada se sirve desde el mismo núcleo: un solo programa.
    # Se monta al final para que no tape las rutas /api.
    if settings.app_dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.app_dist_dir, html=True), name="app")

    return app


async def _voice_connection(socket: WebSocket, voice: VoiceSession) -> None:
    """Protocolo de voz con la app.

    La app envía {"tipo": "hablar_inicio"} y luego audio PCM en binario. Azul
    avisa {"tipo": "escucha_terminada"} cuando detecta que el usuario dejó de
    hablar; la app también puede cortar antes con {"tipo": "hablar_fin"}.
    {"tipo": "parar"} interrumpe la respuesta. Azul responde con eventos JSON
    y el audio de cada frase como MP3 en binario.
    """
    await socket.accept()
    current: asyncio.Task[None] | None = None
    audio: asyncio.Queue[bytes | None] | None = None

    async def run(queue: asyncio.Queue[bytes | None]) -> None:
        async def chunks() -> AsyncIterator[bytes]:
            while (chunk := await queue.get()) is not None:
                yield chunk

        try:
            # Marca el inicio del turno: la app descarta el audio que llegue de turnos anteriores.
            await socket.send_json({"tipo": "turno"})
            async with aclosing(voice.handle(chunks())) as events:
                async for event in events:
                    if isinstance(event, Speech):
                        await socket.send_bytes(event.audio)
                    else:
                        await socket.send_json(_voice_event_to_dict(event))
            await socket.send_json({"tipo": "fin"})
        except Exception:
            log.exception("Fallo en la sesión de voz")
            with suppress(Exception):
                await socket.send_json(
                    {"tipo": "error", "mensaje": "Algo falló con la voz. Quedó en el registro."}
                )

    async def interrupt() -> None:
        nonlocal current, audio
        if audio is not None:
            audio.put_nowait(None)
            audio = None
        if current is not None and not current.done():
            current.cancel()
            with suppress(asyncio.CancelledError):
                await current
            await socket.send_json({"tipo": "parado"})
        current = None

    try:
        while True:
            message = await socket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                if audio is not None:
                    audio.put_nowait(message["bytes"])
                continue
            command = json.loads(message.get("text") or "{}").get("tipo")
            if command == "hablar_inicio":
                await interrupt()
                audio = asyncio.Queue()
                current = asyncio.create_task(run(audio))
            elif command == "hablar_fin" and audio is not None:
                audio.put_nowait(None)
                audio = None
            elif command == "parar":
                await interrupt()
    finally:
        if current is not None:
            current.cancel()
            with suppress(asyncio.CancelledError):
                await current


def _event_to_dict(event: ReplyEvent) -> dict[str, Any]:
    match event:
        case TextChunk(text):
            return {"tipo": "texto", "texto": text}
        case SearchNotice():
            return {"tipo": "buscando"}
        case BudgetNotice(level, spent, limit):
            return {
                "tipo": "gasto",
                "nivel": "bloqueo" if level == "blocked" else "aviso",
                "gastado": round(spent, 2),
                "limite": limit,
            }
        case ErrorNotice(message):
            return {"tipo": "error", "mensaje": message}


def _voice_event_to_dict(event: VoiceEvent) -> dict[str, Any]:
    match event:
        case Heard(text, is_final):
            return {"tipo": "escuchado", "texto": text, "final": is_final}
        case Stopped():
            return {"tipo": "parado"}
        case NothingHeard():
            return {"tipo": "nada_escuchado"}
        case ListeningEnded():
            return {"tipo": "escucha_terminada"}
        case _:
            return _event_to_dict(event)


def _ndjson(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False) + "\n"


def run() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    try:
        for path in backup_if_due(
            settings.db_path, settings.backup_destinations, keep=settings.backups_to_keep
        ):
            log.info("Respaldo automático del día: %s", path)
    except Exception:
        # Un respaldo fallido no debe impedir que Azul arranque.
        log.exception("No se pudo hacer el respaldo automático")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
