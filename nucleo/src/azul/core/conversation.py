"""Conversación: une memoria, cerebro y control de gasto en cada mensaje."""

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

from azul.core.effort import choose_effort
from azul.core.notes import FactNotes
from azul.core.persona import build_system_prompt
from azul.core.ports import (
    Brain,
    BrainError,
    BrainRequest,
    Fact,
    MemoryStore,
    Message,
    Searching,
    ToolSpec,
    Usage,
    UsageMeter,
    WeatherError,
    WeatherProvider,
)

log = logging.getLogger(__name__)

HISTORY_LIMIT = 40
MAX_FACT_CHARS = 300
# La caché del proveedor dura 5 minutos; con 4 hay margen.
CACHE_FRESH_SECONDS = 240

WEB_SEARCH = "búsqueda web"
# La escribe el sistema, nunca el modelo (ver persona.py).
CONSULTED_MARK = "⟦consultado: {}⟧"

_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass(frozen=True)
class TextChunk:
    text: str


@dataclass(frozen=True)
class BudgetNotice:
    level: Literal["warning", "blocked"]
    spent_usd: float
    limit_usd: float


@dataclass(frozen=True)
class ErrorNotice:
    message: str


@dataclass(frozen=True)
class SearchNotice:
    """Azul está buscando en internet; la respuesta tardará unos segundos más."""


ReplyEvent = TextChunk | SearchNotice | BudgetNotice | ErrorNotice


class Conversation:
    def __init__(
        self,
        brain: Brain,
        memory: MemoryStore,
        meter: UsageMeter,
        *,
        monthly_budget_usd: float,
        budget_warning_usd: float,
        weather: WeatherProvider | None = None,
        now: Callable[[], datetime] = datetime.now,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._brain = brain
        self._memory = memory
        self._meter = meter
        self._budget = monthly_budget_usd
        self._warning = budget_warning_usd
        self._weather = weather
        self._now = now
        self._clock = clock
        self._last_brain_call: float | None = None
        self._consulted: list[str] = []
        # Mismo orden y definición en cada solicitud: así las herramientas quedan en caché.
        self._tools: list[ToolSpec] = []
        if weather is not None:
            self._tools.append(
                ToolSpec(
                    name="clima",
                    description=(
                        "Clima actual y pronóstico de un lugar (Open-Meteo). Úsala para cualquier "
                        "pregunta del clima en vez de la búsqueda web: es mucho más rápida."
                    ),
                    input_schema={
                        "type": "object",
                        "properties": {
                            "lugar": {
                                "type": "string",
                                "description": "Ciudad, y si ayuda, región o país. "
                                "Ej.: 'Villavicencio, Colombia'.",
                            },
                            "dias": {
                                "type": "integer",
                                "description": "Días de pronóstico, de 1 a 7.",
                            },
                        },
                        "required": ["lugar", "dias"],
                        "additionalProperties": False,
                    },
                    handler=self._weather_tool,
                )
            )

    async def reply(self, user_text: str) -> AsyncIterator[ReplyEvent]:
        spent = await self._meter.month_total_usd()
        if spent >= self._budget:
            yield BudgetNotice("blocked", spent, self._budget)
            return

        await self._memory.add_message(Message("user", user_text))
        request = BrainRequest(
            system=build_system_prompt(await self._memory.facts()),
            messages=_for_brain(
                _starting_with_user(await self._memory.recent_messages(HISTORY_LIMIT))
            ),
            effort=choose_effort(user_text),
            context=self._context(),
            tools=self._tools,
        )
        self._last_brain_call = self._clock()

        parts: list[str] = []
        notes = FactNotes()
        # Lo que se consulta de verdad en esta respuesta queda guardado con ella (ADR 0027).
        self._consulted = consulted = []
        try:
            # aclosing: si el usuario interrumpe, el cerebro se cierra de inmediato.
            async with aclosing(self._brain.respond(request)) as events:
                async for event in events:
                    if isinstance(event, Usage):
                        await self._meter.record(event)
                    elif isinstance(event, Searching):
                        if WEB_SEARCH not in consulted:
                            consulted.append(WEB_SEARCH)
                            yield SearchNotice()
                    else:
                        visible, facts = notes.feed(event)
                        for fact in facts:
                            await self._save_fact(fact)
                        if visible:
                            parts.append(visible)
                            yield TextChunk(visible)
            rest = notes.flush()
            if rest:
                parts.append(rest)
                yield TextChunk(rest)
        except BrainError as error:
            yield ErrorNotice(str(error))
        except Exception:
            # Un fallo inesperado no debe cortar la conversación sin explicación.
            log.exception("Fallo inesperado del cerebro")
            yield ErrorNotice("Algo falló de mi lado. Quedó anotado en el registro técnico.")
        finally:
            # También se guarda una respuesta interrumpida: es lo que el usuario alcanzó a recibir.
            answer = "".join(parts).strip()
            if answer:
                await self._memory.add_message(
                    Message("assistant", answer, consulted="; ".join(consulted))
                )

        spent = await self._meter.month_total_usd()
        if spent >= self._budget:
            yield BudgetNotice("blocked", spent, self._budget)
        elif spent >= self._warning:
            yield BudgetNotice("warning", spent, self._budget)

    async def prewarm(self) -> None:
        """Prepara la caché del cerebro mientras el usuario todavía está hablando.

        Solo actúa si la caché probablemente venció; si no, sería un gasto inútil.
        """
        now = self._clock()
        if self._last_brain_call is not None and now - self._last_brain_call < CACHE_FRESH_SECONDS:
            return
        if await self._meter.month_total_usd() >= self._budget:
            return
        self._last_brain_call = now
        # Un mensaje menos que reply(): ahí se suma el mensaje nuevo y el prefijo coincide.
        history = await self._memory.recent_messages(HISTORY_LIMIT - 1)
        request = BrainRequest(
            system=build_system_prompt(await self._memory.facts()),
            messages=_for_brain(_starting_with_user(history)),
            tools=self._tools,
        )
        usage = await self._brain.prewarm(request)
        if usage:
            await self._meter.record(usage)

    async def _save_fact(self, fact: str) -> None:
        if len(fact) > MAX_FACT_CHARS:
            log.warning("Dato de %d caracteres descartado por largo", len(fact))
            return
        await self._memory.add_fact(Fact(fact))

    async def _weather_tool(self, tool_input: dict[str, Any]) -> str:
        assert self._weather is not None
        place = tool_input.get("lugar")
        if not isinstance(place, str) or not place.strip():
            raise ValueError("Falta el lugar.")
        days = tool_input.get("dias")
        days = days if isinstance(days, int) else 1
        try:
            forecast = await self._weather.forecast(place.strip(), days)
        except WeatherError as error:
            raise ValueError(str(error)) from error
        self._consulted.append(f"clima de {forecast.get('lugar', place.strip())}")
        return json.dumps(forecast, ensure_ascii=False)

    def _context(self) -> str:
        now = self._now()
        return (
            f"Fecha y hora actual del usuario: {_WEEKDAYS[now.weekday()]} {now.day} de "
            f"{_MONTHS[now.month - 1]} de {now.year}, {now:%H:%M}."
        )


def _for_brain(messages: list[Message]) -> list[Message]:
    """Agrega a cada respuesta pasada la marca de lo que se consultó de verdad.

    Sin ella, Azul veía en su historial "lo busqué" sin rastro de la búsqueda y
    concluía, en falso, que había mentido (ADR 0027).
    """
    return [
        replace(message, text=f"{message.text}\n\n{CONSULTED_MARK.format(message.consulted)}")
        if message.role == "assistant" and message.consulted
        else message
        for message in messages
    ]


def _starting_with_user(messages: list[Message]) -> list[Message]:
    """La API exige que la conversación empiece con un mensaje del usuario."""
    for index, message in enumerate(messages):
        if message.role == "user":
            return messages[index:]
    return []
