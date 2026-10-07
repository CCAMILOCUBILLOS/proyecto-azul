"""WhatsApp Business de Meta (Cloud API) para el número de Azul (ADR 0038).

- Enviar: texto (partido en trozos si es muy largo) y plantillas aprobadas.
- Recibir: un servidor aparte, solo con la ruta /whatsapp, que Tailscale Funnel
  publica en internet. Cada aviso de Meta se comprueba con la firma secreta de la
  app; sin firma válida no se procesa nada.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2
from fastapi import FastAPI, Query, Request, Response

from azul.core.ports import MensajeEntrante, WhatsAppError

log = logging.getLogger(__name__)

API = "https://graph.facebook.com"
TIMEOUT_SECONDS = 20.0
MAX_CARACTERES = 4000  # WhatsApp acepta 4096 por mensaje
# Meta rechaza escribir libremente pasadas 24 h desde el último mensaje de la persona.
_FUERA_DE_VENTANA = {131047, 131026}


class WhatsAppMeta:
    def __init__(
        self,
        token: str,
        numero_id: str,
        version: str = "v23.0",
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"{API}/{version}/{numero_id}/messages"
        self._token = token
        self._transport = transport

    async def enviar(self, numero: str, texto: str) -> None:
        for trozo in _trozos(texto.strip()):
            await self._publicar(
                {"to": numero, "type": "text", "text": {"body": trozo, "preview_url": False}}
            )

    async def enviar_plantilla(self, numero: str, plantilla: str) -> None:
        await self._publicar(
            {
                "to": numero,
                "type": "template",
                "template": {"name": plantilla, "language": {"code": "es"}},
            }
        )

    async def enviar_audio(self, numero: str, mp3: bytes) -> None:
        # Primero se sube el audio a Meta; luego se envía por su id.
        try:
            async with httpx2.AsyncClient(
                timeout=TIMEOUT_SECONDS, transport=self._transport
            ) as cliente:
                respuesta = await cliente.post(
                    self._url.removesuffix("/messages") + "/media",
                    headers={"Authorization": f"Bearer {self._token}"},
                    data={"messaging_product": "whatsapp", "type": "audio/mpeg"},
                    files={"file": ("azul.mp3", mp3, "audio/mpeg")},
                )
        except httpx2.HTTPError as error:
            raise WhatsAppError("No pude subir el audio a WhatsApp.") from error
        if respuesta.status_code >= 400:
            log.warning("WhatsApp rechazó el audio: HTTP %s", respuesta.status_code)
            raise WhatsAppError("WhatsApp no aceptó el audio.")
        await self._publicar(
            {"to": numero, "type": "audio", "audio": {"id": respuesta.json()["id"]}}
        )

    async def _publicar(self, cuerpo: dict[str, Any]) -> None:
        try:
            async with httpx2.AsyncClient(
                timeout=TIMEOUT_SECONDS, transport=self._transport
            ) as cliente:
                respuesta = await cliente.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._token}"},
                    json={
                        "messaging_product": "whatsapp",
                        "recipient_type": "individual",
                        **cuerpo,
                    },
                )
        except httpx2.HTTPError as error:
            log.warning("WhatsApp no respondió: %s", type(error).__name__)
            raise WhatsAppError("No pude conectarme con WhatsApp.") from error
        if respuesta.status_code >= 400:
            codigo = _codigo_de_error(respuesta)
            # Solo el código: el cuerpo puede repetir el texto del mensaje.
            log.warning(
                "WhatsApp rechazó un envío: HTTP %s, código %s", respuesta.status_code, codigo
            )
            if codigo in _FUERA_DE_VENTANA:
                raise WhatsAppError(
                    "WhatsApp solo deja escribirle a alguien dentro de las 24 horas siguientes a "
                    "su último mensaje."
                )
            if respuesta.status_code == 401:
                raise WhatsAppError("El token de WhatsApp venció o no es válido.")
            raise WhatsAppError("WhatsApp no aceptó el mensaje.")


def crear_receptor(
    secreto_app: str,
    token_verificacion: str,
    al_recibir: Callable[[MensajeEntrante], Awaitable[None]],
) -> FastAPI:
    """El servidor que Meta llama. Solo tiene /whatsapp: nada más de Azul queda expuesto."""
    receptor = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    en_curso: set[asyncio.Task[None]] = set()

    @receptor.get("/whatsapp")
    async def verificar(
        modo: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        reto: str = Query("", alias="hub.challenge"),
    ) -> Response:
        # Meta lo llama una vez al configurar la dirección, para comprobar que es nuestra.
        if modo == "subscribe" and hmac.compare_digest(token, token_verificacion):
            return Response(reto, media_type="text/plain")
        return Response(status_code=403)

    @receptor.post("/whatsapp")
    async def recibir(request: Request) -> Response:
        cuerpo = await request.body()
        if not firma_valida(secreto_app, cuerpo, request.headers.get("x-hub-signature-256", "")):
            log.warning("Aviso de WhatsApp con firma inválida: descartado")
            return Response(status_code=401)
        try:
            datos = json.loads(cuerpo)
        except ValueError:
            return Response(status_code=400)
        for mensaje in mensajes_de(datos):
            tarea = asyncio.create_task(_atender(al_recibir, mensaje))
            en_curso.add(tarea)
            tarea.add_done_callback(en_curso.discard)
        # Se responde de inmediato: si Meta espera mucho, reintenta y duplica.
        return Response(status_code=200)

    return receptor


def firma_valida(secreto: str, cuerpo: bytes, cabecera: str) -> bool:
    if not secreto or not cabecera.startswith("sha256="):
        return False
    esperada = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, cabecera.removeprefix("sha256="))


def mensajes_de(datos: dict[str, Any]) -> list[MensajeEntrante]:
    """Los mensajes de un aviso de Meta (ignora confirmaciones de entrega y lectura)."""
    mensajes = []
    for entrada in datos.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            valor = cambio.get("value") or {}
            nombres = {
                c.get("wa_id"): (c.get("profile") or {}).get("name", "")
                for c in valor.get("contacts") or []
            }
            for m in valor.get("messages") or []:
                de = str(m.get("from") or "")
                if not de or not m.get("id"):
                    continue
                tipo = str(m.get("type") or "")
                texto = (m.get("text") or {}).get("body", "") if tipo == "text" else ""
                mensajes.append(
                    MensajeEntrante(
                        id=str(m["id"]),
                        de=de,
                        nombre=str(nombres.get(de) or ""),
                        tipo=tipo,
                        texto=str(texto),
                    )
                )
    return mensajes


async def _atender(
    al_recibir: Callable[[MensajeEntrante], Awaitable[None]], mensaje: MensajeEntrante
) -> None:
    try:
        await al_recibir(mensaje)
    except Exception:
        log.exception("Fallo atendiendo un mensaje de WhatsApp")


def _trozos(texto: str) -> list[str]:
    trozos = []
    while len(texto) > MAX_CARACTERES:
        corte = texto.rfind("\n", 0, MAX_CARACTERES)
        if corte < MAX_CARACTERES // 2:
            corte = texto.rfind(" ", 0, MAX_CARACTERES)
        if corte <= 0:
            corte = MAX_CARACTERES
        trozos.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    return [*trozos, texto] if texto else trozos


def _codigo_de_error(respuesta: httpx2.Response) -> int | None:
    try:
        return int(respuesta.json()["error"]["code"])
    except (ValueError, KeyError, TypeError):
        return None
