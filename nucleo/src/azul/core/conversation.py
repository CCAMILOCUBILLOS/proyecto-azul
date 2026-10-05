"""Conversación: une memoria, cerebro y control de gasto en cada mensaje."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from azul.core.effort import choose_effort
from azul.core.persona import build_system_prompt
from azul.core.ports import (
    Brain,
    BrainError,
    BrainRequest,
    Fact,
    MemoryStore,
    Message,
    ToolSpec,
    Usage,
    UsageMeter,
)

log = logging.getLogger(__name__)

HISTORY_LIMIT = 40
MAX_FACT_CHARS = 300

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


ReplyEvent = TextChunk | BudgetNotice | ErrorNotice


class Conversation:
    def __init__(
        self,
        brain: Brain,
        memory: MemoryStore,
        meter: UsageMeter,
        *,
        monthly_budget_usd: float,
        budget_warning_usd: float,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._brain = brain
        self._memory = memory
        self._meter = meter
        self._budget = monthly_budget_usd
        self._warning = budget_warning_usd
        self._now = now
        self._remember_tool = ToolSpec(
            name="remember",
            description=(
                "Guarda un dato duradero e importante sobre el usuario para recordarlo en "
                "futuras conversaciones. Escríbelo en una frase, en tercera persona."
            ),
            input_schema={
                "type": "object",
                "properties": {"fact": {"type": "string", "description": "El dato a recordar."}},
                "required": ["fact"],
                "additionalProperties": False,
            },
            handler=self._remember,
        )

    async def reply(self, user_text: str) -> AsyncIterator[ReplyEvent]:
        spent = await self._meter.month_total_usd()
        if spent >= self._budget:
            yield BudgetNotice("blocked", spent, self._budget)
            return

        await self._memory.add_message(Message("user", user_text))
        request = BrainRequest(
            system=build_system_prompt(await self._memory.facts()),
            messages=_starting_with_user(await self._memory.recent_messages(HISTORY_LIMIT)),
            effort=choose_effort(user_text),
            context=self._context(),
            tools=[self._remember_tool],
        )

        parts: list[str] = []
        try:
            # aclosing: si el usuario interrumpe, el cerebro se cierra de inmediato.
            async with aclosing(self._brain.respond(request)) as events:
                async for event in events:
                    if isinstance(event, Usage):
                        await self._meter.record(event)
                    else:
                        parts.append(event)
                        yield TextChunk(event)
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
                await self._memory.add_message(Message("assistant", answer))

        spent = await self._meter.month_total_usd()
        if spent >= self._budget:
            yield BudgetNotice("blocked", spent, self._budget)
        elif spent >= self._warning:
            yield BudgetNotice("warning", spent, self._budget)

    async def _remember(self, tool_input: dict[str, Any]) -> str:
        fact = tool_input.get("fact")
        if not isinstance(fact, str) or not fact.strip():
            raise ValueError("El dato está vacío.")
        fact = fact.strip()
        if len(fact) > MAX_FACT_CHARS:
            raise ValueError(f"El dato es demasiado largo (máximo {MAX_FACT_CHARS} caracteres).")
        is_new = await self._memory.add_fact(Fact(fact))
        return "Guardado." if is_new else "Ya lo tenías guardado."

    def _context(self) -> str:
        now = self._now()
        return (
            f"Fecha y hora actual del usuario: {_WEEKDAYS[now.weekday()]} {now.day} de "
            f"{_MONTHS[now.month - 1]} de {now.year}, {now:%H:%M}."
        )


def _starting_with_user(messages: list[Message]) -> list[Message]:
    """La API exige que la conversación empiece con un mensaje del usuario."""
    for index, message in enumerate(messages):
        if message.role == "user":
            return messages[index:]
    return []
