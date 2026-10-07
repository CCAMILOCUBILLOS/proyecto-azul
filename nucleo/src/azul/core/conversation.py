"""Conversación: une memoria, cerebro y control de gasto en cada mensaje."""

import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

from azul.core.effort import choose_effort
from azul.core.herramientas_correo import herramientas_correo
from azul.core.herramientas_documentos import herramienta_habilidades, herramientas_documentos
from azul.core.notes import FactNotes
from azul.core.persona import build_system_prompt
from azul.core.ports import (
    Brain,
    BrainError,
    BrainRequest,
    Correo,
    Documentos,
    Fact,
    Habilidad,
    MemoryStore,
    Message,
    RedNacional,
    Searching,
    ToolSpec,
    Usage,
    UsageMeter,
    WeatherError,
    WeatherProvider,
)
from azul.core.red_nacional import herramientas_red_nacional

log = logging.getLogger(__name__)

# Ventana del historial que ve el cerebro: entre 40 y 59 mensajes. Su inicio se mueve
# de a 20 mensajes, no en cada turno: así el historial sigue en la caché del
# proveedor (que se paga al 10 %) y solo se reescribe una vez cada 10 turnos.
HISTORY_MIN = 40
HISTORY_STEP = 20
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
        red_nacional: RedNacional | None = None,
        habilidades: Sequence[Habilidad] = (),
        documentos: Documentos | None = None,
        correo: Correo | None = None,
        herramientas_extra: Sequence[ToolSpec] = (),
        # WhatsApp (ADR 0038): con otra persona cambian las instrucciones y cada
        # herramienta pasa por los permisos que el usuario le enseñó a Azul.
        instrucciones: Callable[[list[Fact], Sequence[Habilidad]], str] = build_system_prompt,
        envolver_herramienta: Callable[[ToolSpec], ToolSpec] | None = None,
        contexto_extra: Callable[[], Awaitable[str]] | None = None,
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
        if red_nacional is not None:
            self._tools.extend(herramientas_red_nacional(red_nacional, self._anotar))
        # Habilidades (ADR 0032): la lista va en las instrucciones; el detalle, con una herramienta.
        self._habilidades = list(habilidades)
        usar_habilidad = herramienta_habilidades(self._habilidades)
        if usar_habilidad is not None:
            self._tools.append(usar_habilidad)
        if documentos is not None:
            self._tools.extend(herramientas_documentos(documentos, self._anotar))
        if correo is not None:
            self._tools.extend(herramientas_correo(correo, self._anotar))
        self._tools.extend(herramientas_extra)
        if envolver_herramienta is not None:
            self._tools = [envolver_herramienta(tool) for tool in self._tools]
        self._instrucciones = instrucciones
        self._contexto_extra = contexto_extra

    async def reply(self, user_text: str) -> AsyncIterator[ReplyEvent]:
        spent = await self._meter.month_total_usd()
        if spent >= self._budget:
            yield BudgetNotice("blocked", spent, self._budget)
            return

        await self._memory.add_message(Message("user", user_text))
        request = BrainRequest(
            system=self._instrucciones(await self._memory.facts(), self._habilidades),
            messages=_for_brain(_starting_with_user(await self._history(including_new=True))),
            effort=choose_effort(user_text),
            context=await self._context_completo(),
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

    def nombres_de_herramientas(self) -> list[str]:
        return [tool.name for tool in self._tools]

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
        # La misma ventana que usará reply(), sin el mensaje que aún no llega: el prefijo coincide.
        history = await self._history(including_new=False)
        request = BrainRequest(
            system=self._instrucciones(await self._memory.facts(), self._habilidades),
            messages=_for_brain(_starting_with_user(history)),
            tools=self._tools,
        )
        usage = await self._brain.prewarm(request)
        if usage:
            await self._meter.record(usage)

    async def _history(self, *, including_new: bool) -> list[Message]:
        """Los mensajes recientes que ve el cerebro, con el inicio estable (ver HISTORY_STEP)."""
        stored = await self._memory.message_count()
        total = stored if including_new else stored + 1
        window = HISTORY_MIN + total % HISTORY_STEP
        return await self._memory.recent_messages(window if including_new else window - 1)

    async def conocimiento(self) -> dict[str, Any]:
        """Lo que Azul sabe y sabe hacer: la app dibuja su red neuronal con esto.

        Las etiquetas son lo que se ve al pasar el cursor por cada neurona.
        """
        facts = await self._memory.facts()
        # La búsqueda web la pone el cerebro; las demás, este núcleo.
        herramientas = [
            "busqueda_web",
            *(t.name for t in self._tools if t.name != "usar_habilidad"),
        ]
        return {
            "recuerdos": len(facts),
            "habilidades": [h.nombre for h in self._habilidades],
            "herramientas": herramientas,
            "mensajes": await self._memory.message_count(),
            "etiquetas": {
                "recuerdos": [fact.text for fact in facts],
                "habilidades": {h.nombre: _resumen(h.descripcion) for h in self._habilidades},
                "herramientas": {n: _NOMBRES_DE_HERRAMIENTAS.get(n, n) for n in herramientas},
            },
        }

    def _anotar(self, consultado: str) -> None:
        # Lo consultado se guarda una vez por respuesta (ADR 0027).
        if consultado not in self._consulted:
            self._consulted.append(consultado)

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

    async def _context_completo(self) -> str:
        extra = await self._contexto_extra() if self._contexto_extra else ""
        return f"{self._context()}\n\n{extra}" if extra else self._context()

    def _context(self) -> str:
        now = self._now()
        return (
            f"Fecha y hora actual del usuario: {_WEEKDAYS[now.weekday()]} {now.day} de "
            f"{_MONTHS[now.month - 1]} de {now.year}, {now:%H:%M}."
        )


_NOMBRES_DE_HERRAMIENTAS = {
    "busqueda_web": "Búsqueda en internet",
    "clima": "Clima",
    "buscar_archivos": "Buscar archivos en el PC",
    "leer_documento": "Leer documentos",
    "pdf_a_word": "Convertir PDF a Word",
    "crear_word": "Crear documentos Word",
    "crear_excel": "Crear Excel",
    "guardar_archivo": "Guardar páginas y código",
    "correo_buscar": "Outlook: buscar correos",
    "correo_leer": "Outlook: leer correos",
    "correo_borrador": "Outlook: redactar borradores",
    "correo_responder": "Outlook: responder en borrador",
    "whatsapp_pendientes": "WhatsApp: pendientes",
    "whatsapp_decidir": "WhatsApp: decidir respuestas",
    "whatsapp_enviar": "WhatsApp: escribir a un contacto",
    "whatsapp_contactos": "WhatsApp: contactos y reglas",
    "whatsapp_regla": "WhatsApp: enseñar reglas",
    "whatsapp_olvidar_regla": "WhatsApp: olvidar reglas",
    "red_nacional_consultar": "Red Nacional: consultas",
    "red_nacional_ejecutar": "Red Nacional: procesos",
}


def nombre_de_herramienta(nombre: str) -> str:
    """El nombre legible de una herramienta (para la red neuronal y los avisos)."""
    return _NOMBRES_DE_HERRAMIENTAS.get(nombre, nombre)


def _resumen(descripcion: str) -> str:
    """La primera idea de la descripción de una habilidad, corta para una etiqueta."""
    primera = descripcion.split(". ")[0].split(" - ")[0].strip().rstrip(".")
    return primera if len(primera) <= 90 else primera[:87].rstrip() + "…"


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
