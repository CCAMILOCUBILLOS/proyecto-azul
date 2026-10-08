"""Punto de entrada: crea la aplicación web y arranca el servidor."""

import asyncio
import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager, suppress
from logging.handlers import RotatingFileHandler
from pathlib import Path
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
from azul.adapters.archivos_equipo import archivos_locales, archivos_remotos
from azul.adapters.correo_outlook import CorreoOutlook
from azul.adapters.correo_remoto import ejecutor_remoto
from azul.adapters.deepgram import DeepgramSpeechToText, DeepgramTextToSpeech, UnconfiguredVoice
from azul.adapters.documentos_windows import DocumentosWindows, raices_por_defecto
from azul.adapters.habilidades_archivos import cargar_habilidades
from azul.adapters.open_meteo import OpenMeteoWeather
from azul.adapters.sqlite_store import SqliteStore
from azul.adapters.tablero_red_nacional import TableroRedNacional
from azul.adapters.verificador_vosk import cargar_verificador
from azul.adapters.whatsapp_meta import WhatsAppMeta, crear_receptor
from azul.backup import backup_if_due
from azul.config import Settings, get_settings
from azul.core.bandeja import RevisorDeCorreo
from azul.core.conversation import (
    BudgetNotice,
    Conversation,
    ErrorNotice,
    ReplyEvent,
    SearchNotice,
    TextChunk,
)
from azul.core.herramientas_archivos import Confirmaciones, herramientas_archivos
from azul.core.ports import (
    Archivos,
    Brain,
    Correo,
    Documentos,
    MemoryStore,
    RedNacional,
    SpeechToText,
    TextToSpeech,
    Usage,
    VerificadorDeVoz,
    WeatherProvider,
    WhatsApp,
)
from azul.core.voice import (
    Heard,
    ListeningEnded,
    NotForAzul,
    NothingHeard,
    Speech,
    Stopped,
    VoiceEvent,
    VoiceSession,
    WakeOnly,
)
from azul.core.whatsapp import Recepcionista

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
        deep_model=settings.brain_model_deep,
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


def build_documentos(settings: Settings) -> Documentos | None:
    if not settings.documentos_activos:
        return None
    return DocumentosWindows(raices_por_defecto(), settings.documentos_salida)


def build_correo(settings: Settings) -> Correo | None:
    if settings.correo_remoto_url and settings.correo_remoto_clave is not None:
        return CorreoOutlook(
            ejecutor_remoto(
                settings.correo_remoto_url, settings.correo_remoto_clave.get_secret_value()
            ),
            firma=settings.correo_firma,
        )
    if not settings.correo_activo or sys.platform != "win32":
        return None
    return CorreoOutlook(firma=settings.correo_firma)


def build_equipos(settings: Settings) -> dict[str, Archivos]:
    """El portátil y, si el ayudante está conectado, el PC de Optometría (ADR 0041)."""
    if not settings.archivos_activos:
        return {}
    equipos: dict[str, Archivos] = {
        "portatil": archivos_locales(settings.archivos_respaldos, settings.archivos_trabajo)
    }
    if settings.correo_remoto_url and settings.correo_remoto_clave is not None:
        equipos["optometria"] = archivos_remotos(
            settings.correo_remoto_url, settings.correo_remoto_clave.get_secret_value()
        )
    return equipos


def build_whatsapp(settings: Settings) -> WhatsApp | None:
    if settings.whatsapp_token is None or not settings.whatsapp_numero_id:
        return None
    return WhatsAppMeta(
        settings.whatsapp_token.get_secret_value(),
        settings.whatsapp_numero_id,
        settings.whatsapp_api_version,
    )


def build_red_nacional(settings: Settings) -> RedNacional | None:
    if not settings.red_nacional_url:
        return None
    return TableroRedNacional(settings.red_nacional_url)


def create_app(
    settings: Settings | None = None,
    *,
    brain: Brain | None = None,
    stt: SpeechToText | None = None,
    tts: TextToSpeech | None = None,
    weather: WeatherProvider | None = None,
    red_nacional: RedNacional | None = None,
    documentos: Documentos | None = None,
    correo: Correo | None = None,
    verificador: VerificadorDeVoz | None = None,
    whatsapp: WhatsApp | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    store = SqliteStore(settings.data_dir / "azul.db")
    # Las mismas piezas sirven a la conversación del usuario y a las de WhatsApp.
    piezas: dict[str, Any] = {
        "weather": weather or OpenMeteoWeather(),
        "red_nacional": red_nacional or build_red_nacional(settings),
        "habilidades": cargar_habilidades(settings.habilidades_dir),
        "documentos": documentos or build_documentos(settings),
        "correo": correo or build_correo(settings),
    }
    cerebro = brain or build_brain(settings)

    def nueva_conversacion(memoria: MemoryStore, **extra: Any) -> Conversation:
        return Conversation(
            cerebro,
            memory=memoria,
            meter=store,
            monthly_budget_usd=settings.monthly_budget_usd,
            budget_warning_usd=settings.budget_warning_usd,
            **piezas,
            **extra,
        )

    if stt is None or tts is None:
        default_stt, default_tts = build_voice(settings)
        stt, tts = stt or default_stt, tts or default_tts

    async def voz_de_azul(texto: str) -> bytes:
        partes = []
        async for parte in tts.synthesize(texto):
            if isinstance(parte, Usage):
                await store.record(parte)
            else:
                partes.append(parte)
        return b"".join(partes)

    whatsapp = whatsapp or build_whatsapp(settings)
    recepcionista = (
        Recepcionista(
            whatsapp,
            store,
            settings.whatsapp_dueno,
            plantilla_aviso=settings.whatsapp_plantilla_aviso,
            voz=voz_de_azul,
        )
        if whatsapp is not None and settings.whatsapp_dueno
        else None
    )
    revisor = (
        RevisorDeCorreo(
            piezas["correo"],
            cerebro,
            store,
            store,
            store,
            monthly_budget_usd=settings.monthly_budget_usd,
            avisar=recepcionista.avisar if recepcionista else None,
            minutos=settings.correo_revision_minutos,
        )
        if piezas["correo"] is not None
        else None
    )
    confirmaciones = Confirmaciones()
    equipos = build_equipos(settings)
    herramientas_extra = [
        *(recepcionista.herramientas_del_dueno() if recepcionista else []),
        *(revisor.herramientas() if revisor else []),
        *(
            herramientas_archivos(equipos, confirmaciones, lambda c: conversation.anotar(c))
            if equipos
            else []
        ),
    ]
    contextos = [
        c
        for c in (recepcionista and recepcionista.contexto_para_dueno, revisor and revisor.contexto)
        if c
    ]

    async def contexto_extra() -> str:
        partes = [await contexto() for contexto in contextos]
        return "\n\n".join(p for p in partes if p)

    conversation = nueva_conversacion(
        store,
        herramientas_extra=herramientas_extra,
        contexto_extra=contexto_extra if contextos else None,
        al_empezar_turno=confirmaciones.nuevo_turno,
    )
    if recepcionista is not None:
        recepcionista.conectar(
            conversation,
            lambda memoria, envolver, instrucciones: nueva_conversacion(
                memoria, envolver_herramienta=envolver, instrucciones=instrucciones
            ),
            nueva_conversacion(store).nombres_de_herramientas(),
        )
    voice = VoiceSession(conversation, stt, tts, meter=store)
    if verificador is None:
        verificador = cargar_verificador(
            settings.escritorio_modelo_voz,
            settings.modelo_hablantes,
            settings.data_dir,
            voz_de_azul=lambda: _frases_de_azul(tts),
        )

    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
        # Revisión periódica de correos (ADR 0039), mientras Azul esté encendida.
        tarea = (
            asyncio.create_task(revisor.vigilar())
            if revisor is not None and settings.correo_revisar
            else None
        )
        yield
        if tarea is not None:
            tarea.cancel()

    app = FastAPI(title="Azul", version=__version__, lifespan=ciclo_de_vida)
    app.state.receptor_whatsapp = (
        crear_receptor(
            settings.whatsapp_secreto_app.get_secret_value(),
            settings.whatsapp_token_verificacion.get_secret_value(),
            recepcionista.recibir,
        )
        if recepcionista is not None
        and settings.whatsapp_secreto_app is not None
        and settings.whatsapp_token_verificacion is not None
        else None
    )

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

    @app.post("/api/preguntar")
    async def preguntar(entrada: ChatInput) -> dict[str, str]:
        """Pregunta y respuesta completas en texto, para el Atajo de Siri (ADR 0026)."""
        parts: list[str] = []
        notices: list[str] = []
        async for event in conversation.reply(entrada.texto.strip()):
            match event:
                case TextChunk(text):
                    parts.append(text)
                case ErrorNotice(message):
                    notices.append(message)
                case BudgetNotice(level="blocked", limit_usd=limit):
                    notices.append(
                        f"Llegaste al límite de {limit:.0f} dólares de este mes; "
                        "estoy en pausa hasta el próximo."
                    )
        answer = "".join(parts).strip()
        return {"respuesta": " ".join([answer, *notices]).strip() or "No tengo respuesta."}

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

    # --- Huella de voz (ADR 0036): el audio llega como PCM de 16 bits a 16 kHz ---

    @app.get("/api/huella")
    async def huella() -> dict[str, Any]:
        return {
            "disponible": verificador is not None,
            "inscrita": bool(verificador and verificador.inscrito),
            "muestras": verificador.muestras if verificador else 0,
        }

    @app.post("/api/huella/muestra")
    async def huella_muestra(request: Request) -> dict[str, int]:
        if verificador is None:
            raise HTTPException(503, "La verificación de voz no está disponible en este equipo.")
        try:
            return {"muestras": await verificador.agregar_muestra(await request.body())}
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.post("/api/huella/listo", status_code=204)
    async def huella_lista() -> Response:
        if verificador is None:
            raise HTTPException(503, "La verificación de voz no está disponible en este equipo.")
        try:
            await verificador.terminar_inscripcion()
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return Response(status_code=204)

    @app.delete("/api/huella", status_code=204)
    async def huella_borrar() -> Response:
        if verificador is not None:
            await verificador.borrar()
        return Response(status_code=204)

    @app.get("/api/conocimiento")
    async def conocimiento() -> dict[str, Any]:
        return await conversation.conocimiento()

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
        await _voice_connection(socket, voice, verificador)

    # La app web compilada se sirve desde el mismo núcleo: un solo programa.
    # Se monta al final para que no tape las rutas /api.
    if settings.app_dist_dir.is_dir():
        app.mount("/", _AppFiles(directory=settings.app_dist_dir, html=True), name="app")

    return app


class _AppFiles(StaticFiles):
    """La app web, siempre en su última versión.

    Los archivos de assets/ llevan un código en el nombre que cambia con cada
    versión, así que pueden guardarse en caché. Las páginas y el manifiesto no:
    sin esto, el navegador seguía mostrando la versión anterior de la app.
    """

    async def get_response(self, path: str, scope) -> Response:  # type: ignore[no-untyped-def]
        response = await super().get_response(path, scope)
        if not scope["path"].startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


async def _voice_connection(
    socket: WebSocket, voice: VoiceSession, verificador: VerificadorDeVoz | None = None
) -> None:
    """Protocolo de voz con la app.

    La app envía {"tipo": "hablar_inicio"} y luego audio PCM en binario. Azul
    avisa {"tipo": "escucha_terminada"} cuando detecta que el usuario dejó de
    hablar; la app también puede cortar antes con {"tipo": "hablar_fin"}.
    {"tipo": "parar"} interrumpe la respuesta. Azul responde con eventos JSON
    y el audio de cada frase como MP3 en binario.

    Interrumpir con la voz (ADR 0036): mientras Azul responde, la app puede
    enviar {"tipo": "interrupcion_inicio"} y el audio de alguien hablando. Si la
    voz es la del usuario, Azul se calla ({"tipo": "interrumpido"}) y ese audio
    abre un turno nuevo; si no, sigue ({"tipo": "no_eres_tu"}).
    """
    await socket.accept()
    current: asyncio.Task[None] | None = None
    audio: asyncio.Queue[bytes | None] | None = None
    posible: list[bytes] | None = None
    llega_audio = asyncio.Event()
    fin_posible = asyncio.Event()
    verificando: asyncio.Task[None] | None = None

    async def run(queue: asyncio.Queue[bytes | None], *, wake: bool) -> None:
        async def chunks() -> AsyncIterator[bytes]:
            while (chunk := await queue.get()) is not None:
                yield chunk

        try:
            # Marca el inicio del turno: la app descarta el audio que llegue de turnos anteriores.
            await socket.send_json({"tipo": "turno"})
            handler = voice.handle_wake if wake else voice.handle
            async with aclosing(handler(chunks())) as events:
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

    async def interrupt(aviso: str | None = "parado") -> None:
        nonlocal current, audio
        if audio is not None:
            audio.put_nowait(None)
            audio = None
        if current is not None and not current.done():
            current.cancel()
            with suppress(asyncio.CancelledError):
                await current
            if aviso:
                await socket.send_json({"tipo": aviso})
        current = None

    async def oir_hasta(bytes_necesarios: int, limite: float) -> None:
        # Se espera a tener voz suficiente para la huella, o a que la persona calle.
        while (
            posible is not None
            and sum(map(len, posible)) < bytes_necesarios
            and not fin_posible.is_set()
            and asyncio.get_running_loop().time() < limite
        ):
            llega_audio.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(llega_audio.wait(), 0.2)

    async def verificar() -> None:
        nonlocal posible, audio, current
        limite = asyncio.get_running_loop().time() + SEGUNDOS_MAXIMOS_VERIFICANDO
        await oir_hasta(BYTES_PARA_VERIFICAR, limite)
        if posible is None or verificador is None:
            return
        veredicto = await verificador.veredicto(b"".join(posible))
        if veredicto == "dudoso" and not fin_posible.is_set():
            # Se parece al usuario, pero no lo bastante: con más voz la huella es más fiable.
            await oir_hasta(BYTES_PARA_DESEMPATAR, limite)
            if posible is None:
                return
            veredicto = await verificador.veredicto(b"".join(posible))
        if veredicto != "si":
            posible = None
            await socket.send_json({"tipo": "no_eres_tu"})
            return
        await interrupt(None)
        await socket.send_json({"tipo": "interrumpido"})
        audio = asyncio.Queue()
        for chunk in posible:
            audio.put_nowait(chunk)
        posible = None
        current = asyncio.create_task(run(audio, wake=False))

    async def cancel_verification() -> None:
        nonlocal posible, verificando
        posible = None
        if verificando is not None and not verificando.done():
            verificando.cancel()
            with suppress(asyncio.CancelledError):
                await verificando
        verificando = None

    try:
        while True:
            message = await socket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                if posible is not None:
                    posible.append(message["bytes"])
                    llega_audio.set()
                elif audio is not None:
                    audio.put_nowait(message["bytes"])
                continue
            command = json.loads(message.get("text") or "{}").get("tipo")
            if command == "interrupcion_inicio":
                if verificador is None or not verificador.inscrito:
                    await socket.send_json({"tipo": "interrupcion_no_disponible"})
                    continue
                await cancel_verification()
                posible = []
                fin_posible.clear()
                verificando = asyncio.create_task(verificar())
            elif command == "interrupcion_fin":
                fin_posible.set()
            elif command in ("hablar_inicio", "activacion_inicio"):
                await cancel_verification()
                await interrupt()
                audio = asyncio.Queue()
                current = asyncio.create_task(run(audio, wake=command == "activacion_inicio"))
            elif command in ("hablar_fin", "activacion_fin") and audio is not None:
                audio.put_nowait(None)
                audio = None
            elif command == "parar":
                await cancel_verification()
                await interrupt()
    finally:
        await cancel_verification()
        if current is not None:
            current.cancel()
            with suppress(asyncio.CancelledError):
                await current


# Interrumpir con la voz (ADR 0036).
# Con menos de ~2 s de voz la huella no distingue bien (medido en el ADR 0036).
BYTES_PARA_VERIFICAR = int(16_000 * 2 * 2.2)  # 2,2 s de voz
BYTES_PARA_DESEMPATAR = int(16_000 * 2 * 3.5)
SEGUNDOS_MAXIMOS_VERIFICANDO = 5.0
_FRASES_DE_AZUL = (
    "Claro, con gusto te ayudo con eso ahora mismo.",
    "Hoy en Villavicencio está haciendo bastante calor.",
    "Listo, ya quedó guardado el documento en tu carpeta.",
    "Te cuento que hay varias órdenes pendientes por cargar.",
    "Mañana tienes una reunión a las diez de la mañana.",
)


async def _frases_de_azul(tts: TextToSpeech) -> list[bytes]:
    """La voz de Azul en PCM de 16 kHz: su huella evita que se interrumpa con su eco."""
    import miniaudio

    frases = []
    for frase in _FRASES_DE_AZUL:
        mp3 = bytearray()
        async with aclosing(tts.synthesize(frase)) as partes:
            async for parte in partes:
                if isinstance(parte, bytes):
                    mp3.extend(parte)
        sonido = miniaudio.decode(
            bytes(mp3),
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=16_000,
        )
        frases.append(sonido.samples.tobytes())
    return frases


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
        case NotForAzul(had_words):
            return {"tipo": "ignorado", "con_palabras": had_words}
        case WakeOnly():
            return {"tipo": "activado"}
        case _:
            return _event_to_dict(event)


def _ndjson(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False) + "\n"


LOG_MAX_BYTES = 1_000_000
LOG_FILES_KEPT = 3


def _configure_logging(log_path: Path) -> None:
    """El registro técnico va a un archivo, no a la ventana.

    En Windows, un clic dentro de la ventana de comandos la pone en modo
    selección y pausa a cualquier programa que escriba en ella: Azul se
    quedaba congelado. Escribiendo en un archivo, eso no puede pasar.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_FILES_KEPT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def run() -> None:
    settings = get_settings()
    log_path = settings.data_dir / "azul.log"
    _configure_logging(log_path)
    try:
        for path in backup_if_due(
            settings.db_path, settings.backup_destinations, keep=settings.backups_to_keep
        ):
            log.info("Respaldo automático del día: %s", path)
    except Exception:
        # Un respaldo fallido no debe impedir que Azul arranque.
        log.exception("No se pudo hacer el respaldo automático")
    print(f"Azul está encendido en http://127.0.0.1:{settings.port}")
    print(f"Registro técnico: {log_path}")
    print("Para apagarlo, cierra esta ventana.", flush=True)
    app = create_app(settings)
    receptor = app.state.receptor_whatsapp
    if receptor is None:
        # log_config=None: uvicorn usa el registro en archivo configurado arriba.
        uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)
        return
    # WhatsApp (ADR 0038): un segundo servidor, solo con /whatsapp, para Tailscale Funnel.
    print(f"Receptor de WhatsApp en http://127.0.0.1:{settings.whatsapp_puerto}/whatsapp")
    servidores = [
        uvicorn.Server(
            uvicorn.Config(app, host=settings.host, port=settings.port, log_config=None)
        ),
        uvicorn.Server(
            uvicorn.Config(
                receptor, host="127.0.0.1", port=settings.whatsapp_puerto, log_config=None
            )
        ),
    ]

    async def ambos() -> None:
        await asyncio.gather(*(servidor.serve() for servidor in servidores))

    asyncio.run(ambos())
