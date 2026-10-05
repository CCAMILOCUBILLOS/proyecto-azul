"""Punto de entrada: crea la aplicación web y arranca el servidor."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import anthropic
import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from azul import __version__
from azul.adapters.anthropic_brain import AnthropicBrain, UnconfiguredBrain
from azul.adapters.sqlite_store import SqliteStore
from azul.config import Settings, get_settings
from azul.core.conversation import BudgetNotice, Conversation, ErrorNotice, ReplyEvent, TextChunk
from azul.core.ports import Brain

MAX_INPUT_CHARS = 4000


class ChatInput(BaseModel):
    texto: str = Field(min_length=1, max_length=MAX_INPUT_CHARS, pattern=r"\S")


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


def create_app(settings: Settings | None = None, *, brain: Brain | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = SqliteStore(settings.data_dir / "azul.db")
    conversation = Conversation(
        brain or build_brain(settings),
        memory=store,
        meter=store,
        monthly_budget_usd=settings.monthly_budget_usd,
        budget_warning_usd=settings.budget_warning_usd,
    )
    app = FastAPI(title="Azul", version=__version__)

    @app.get("/api/salud")
    async def salud() -> dict[str, str]:
        return {"estado": "ok", "version": __version__}

    @app.post("/api/chat")
    async def chat(entrada: ChatInput) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            async for event in conversation.reply(entrada.texto.strip()):
                yield _ndjson(_event_to_dict(event))
            yield _ndjson({"tipo": "fin"})

        return StreamingResponse(events(), media_type="application/x-ndjson")

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

    # La app web compilada se sirve desde el mismo núcleo: un solo programa.
    # Se monta al final para que no tape las rutas /api.
    if settings.app_dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.app_dist_dir, html=True), name="app")

    return app


def _event_to_dict(event: ReplyEvent) -> dict[str, Any]:
    match event:
        case TextChunk(text):
            return {"tipo": "texto", "texto": text}
        case BudgetNotice(level, spent, limit):
            return {
                "tipo": "gasto",
                "nivel": "bloqueo" if level == "blocked" else "aviso",
                "gastado": round(spent, 2),
                "limite": limit,
            }
        case ErrorNotice(message):
            return {"tipo": "error", "mensaje": message}


def _ndjson(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False) + "\n"


def run() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
