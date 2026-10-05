"""Adaptador del cerebro para Claude, de Anthropic (ADR 0005, 0014, 0015)."""

import logging
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from azul.core.ports import (
    BrainError,
    BrainEvent,
    BrainRequest,
    Effort,
    Searching,
    ToolSpec,
    Usage,
)

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
# Vueltas máximas de herramientas en una misma respuesta.
MAX_ROUNDS = 6

FALLBACK_BETA = "server-side-fallback-2026-07-01"
PER_MESSAGE_EFFORT_BETA = "mid-conversation-output-config-2026-07-01"

# USD por millón de tokens: entrada, salida, escritura de caché (5 min), lectura de caché.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 6.25, 0.50),
    "claude-sonnet-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-4-5": (1.00, 5.00, 1.25, 0.10),
}
WEB_SEARCH_USD = 0.01
# Si aparece un modelo sin precio conocido, se cobra como el más caro para no subestimar.
_UNKNOWN_MODEL_PRICE = max(PRICES.values())

REFUSAL_TEXT = "Prefiero no responder a eso. ¿Te ayudo con otra cosa?"


def cost_usd(model: str, usage: Any) -> float:
    price = _price_for(model)
    tokens = (
        getattr(usage, "input_tokens", 0) or 0,
        getattr(usage, "output_tokens", 0) or 0,
        getattr(usage, "cache_creation_input_tokens", 0) or 0,
        getattr(usage, "cache_read_input_tokens", 0) or 0,
    )
    server_tools = getattr(usage, "server_tool_use", None)
    searches = getattr(server_tools, "web_search_requests", 0) or 0
    return sum(n * p for n, p in zip(tokens, price, strict=True)) / 1_000_000 + (
        searches * WEB_SEARCH_USD
    )


def _price_for(model: str) -> tuple[float, float, float, float]:
    # El más específico primero: "claude-opus-5-5" antes que "claude-opus-5".
    for known in sorted(PRICES, key=len, reverse=True):
        if model.startswith(known):
            return PRICES[known]
    log.warning("Modelo sin precio conocido: %s; se usa el precio más alto", model)
    return _UNKNOWN_MODEL_PRICE


class AnthropicBrain:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        *,
        model: str,
        fallbacks: bool = True,
        per_message_effort: bool = True,
        web_search_max_uses: int = 3,
    ) -> None:
        self._client = client
        self._model = model
        self._fallbacks = fallbacks
        self._per_message_effort = per_message_effort
        self._web_search_max_uses = web_search_max_uses

    async def respond(self, request: BrainRequest) -> AsyncIterator[BrainEvent]:
        messages = self._build_messages(request)
        params = self._base_params(request)
        streamed_text = False

        for _ in range(MAX_ROUNDS):
            starting_round = True
            try:
                async with self._client.beta.messages.stream(messages=messages, **params) as stream:
                    async for event in stream:
                        if event.type == "text":
                            # Separa el texto de una vuelta anterior.
                            if starting_round and streamed_text and event.text[:1] not in " \n":
                                yield " "
                            starting_round = False
                            streamed_text = True
                            yield event.text
                        elif event.type == "content_block_start" and _is_search(event):
                            yield Searching()
                    final = await stream.get_final_message()
            except anthropic.APIError as error:
                raise _to_brain_error(error) from error

            yield Usage(
                provider="anthropic",
                cost_usd=cost_usd(final.model, final.usage),
                detail=f"{final.model} · {final.stop_reason}",
            )

            if final.stop_reason == "refusal":
                if not streamed_text:
                    yield REFUSAL_TEXT
                return
            if final.stop_reason == "pause_turn":
                # Una herramienta del servidor (búsqueda web) pidió continuar.
                messages.append({"role": "assistant", "content": final.content})
                continue
            tool_uses = [block for block in final.content if block.type == "tool_use"]
            if final.stop_reason != "tool_use" or not tool_uses:
                return

            messages.append({"role": "assistant", "content": final.content})
            messages.append(
                {
                    "role": "user",
                    "content": [await _run_tool(block, request.tools) for block in tool_uses],
                }
            )

        log.warning("Se alcanzó el máximo de %d vueltas de herramientas", MAX_ROUNDS)

    async def prewarm(self, request: BrainRequest) -> Usage | None:
        """Escribe en caché las instrucciones y el historial antes de que llegue el mensaje.

        Usa max_tokens=0: el proveedor solo procesa el prefijo, sin generar respuesta.
        """
        params = self._base_params(request)
        # La caché se marca en lo compartido con la próxima solicitud real, no al final.
        params.pop("cache_control")
        params.pop("fallbacks", None)
        betas = [beta for beta in params.pop("betas", []) if beta != FALLBACK_BETA]
        if betas:
            params["betas"] = betas
        params["max_tokens"] = 0

        history: list[dict[str, Any]] = [
            {"role": message.role, "content": message.text} for message in request.messages
        ]
        if history:
            last = history[-1]
            history[-1] = {
                "role": last["role"],
                "content": [
                    {
                        "type": "text",
                        "text": last["content"],
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        try:
            response = await self._client.beta.messages.create(
                messages=[*history, {"role": "user", "content": "precalentamiento"}], **params
            )
        except anthropic.APIError as error:
            log.warning("No se pudo precalentar la caché: %s", error)
            return None
        return Usage(
            provider="anthropic",
            cost_usd=cost_usd(response.model, response.usage),
            detail=f"{response.model} · precalentamiento",
        )

    def _build_messages(self, request: BrainRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": message.role, "content": message.text} for message in request.messages
        ]
        if self._per_message_effort and messages:
            # Cambiar el esfuerzo con un mensaje de sistema no invalida la caché;
            # cambiarlo en el parámetro principal, sí.
            last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
            messages.insert(
                last_user,
                {
                    "role": "system",
                    "content": [],
                    "output_config": {"effort": request.effort.value},
                },
            )
        if request.context:
            # Lo volátil va al final para que el resto siga en caché.
            messages.append({"role": "system", "content": request.context})
        return messages

    def _base_params(self, request: BrainRequest) -> dict[str, Any]:
        betas: list[str] = []
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "system": [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ],
            "tools": [
                {
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": self._web_search_max_uses,
                },
                *(_tool_definition(tool) for tool in request.tools),
            ],
            "output_config": {
                "effort": (Effort.MEDIUM if self._per_message_effort else request.effort).value
            },
            "cache_control": {"type": "ephemeral"},
        }
        if self._per_message_effort:
            betas.append(PER_MESSAGE_EFFORT_BETA)
        if self._fallbacks:
            # Si un filtro de seguridad rechaza por error, Anthropic reintenta con otro modelo.
            betas.append(FALLBACK_BETA)
            params["fallbacks"] = "default"
        if betas:
            params["betas"] = betas
        return params


def _is_search(event: Any) -> bool:
    block = event.content_block
    return block.type == "server_tool_use" and getattr(block, "name", "") == "web_search"


def _tool_definition(tool: ToolSpec) -> dict[str, Any]:
    # Sin eager_input_streaming: las entradas son una frase corta y así la API
    # valida el JSON completo antes de entregarlo.
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "strict": True,
    }


async def _run_tool(block: Any, tools: list[ToolSpec]) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "tool_result", "tool_use_id": block.id}
    tool = next((t for t in tools if t.name == block.name), None)
    if tool is None:
        return {**result, "content": f"Herramienta desconocida: {block.name}", "is_error": True}
    if not isinstance(block.input, dict):
        return {**result, "content": "La entrada de la herramienta no es válida.", "is_error": True}
    try:
        return {**result, "content": await tool.handler(block.input)}
    except ValueError as error:
        return {**result, "content": str(error), "is_error": True}


def _to_brain_error(error: anthropic.APIError) -> BrainError:
    log.error("Error de Anthropic: %s", error)
    match error:
        case anthropic.AuthenticationError():
            message = "La clave de Anthropic no es válida. Revisa ANTHROPIC_API_KEY en el .env."
        case anthropic.PermissionDeniedError():
            message = "Tu clave de Anthropic no tiene permiso para usar este modelo."
        case anthropic.RateLimitError():
            message = "Anthropic me está pidiendo ir más despacio. Intenta en un momento."
        case anthropic.BadRequestError() if "credit" in str(error).lower():
            message = "Se acabó el saldo en Anthropic. Recarga crédito en su consola."
        case anthropic.BadRequestError():
            message = "Anthropic rechazó la solicitud. Quedó anotado en el registro técnico."
        case anthropic.APIConnectionError():
            message = "No pude conectarme con Anthropic. Revisa tu conexión a internet."
        case anthropic.APIStatusError() if error.status_code >= 500:
            message = "Anthropic tiene problemas en este momento. Intenta en un rato."
        case _:
            message = "Algo falló al hablar con Anthropic. Quedó anotado en el registro técnico."
    return BrainError(message)


class UnconfiguredBrain:
    """Cerebro de reemplazo mientras no haya clave de Anthropic."""

    async def respond(self, request: BrainRequest) -> AsyncIterator[BrainEvent]:
        raise BrainError(
            "Aún no tengo cerebro: falta la clave de Anthropic. Pégala en el archivo .env "
            "(ANTHROPIC_API_KEY=...) y reinicia Azul."
        )
        yield  # pragma: no cover - convierte la función en generador

    async def prewarm(self, request: BrainRequest) -> Usage | None:
        return None
