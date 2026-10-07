"""Arranca el cliente de voz de escritorio: `python -m azul.escritorio` (ADR 0028)."""

import asyncio
import contextlib
import logging
from logging.handlers import RotatingFileHandler

from pynput import keyboard
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from azul.config import get_settings
from azul.escritorio.audio import Microfono, Parlante
from azul.escritorio.cliente import ClienteEscritorio
from azul.escritorio.horario import parse_hora
from azul.escritorio.palabra_clave import cargar_reconocedor

log = logging.getLogger("azul.escritorio")

REINTENTO_MAXIMO = 15.0


async def ejecutar() -> None:
    settings = get_settings()
    loop = asyncio.get_running_loop()
    url = f"ws://127.0.0.1:{settings.port}/api/voz"
    salida: asyncio.Queue[str | bytes] = asyncio.Queue()
    microfono_cola: asyncio.Queue[bytes] = asyncio.Queue()

    cliente: ClienteEscritorio | None = None
    parlante = Parlante(al_terminar=lambda: loop.call_soon_threadsafe(_avisar_fin_de_audio))

    def _avisar_fin_de_audio() -> None:
        if cliente:
            cliente.termino_el_audio()

    cliente = ClienteEscritorio(
        parlante,
        salida.put_nowait,
        oye_azul=settings.escritorio_oye_azul,
        desde=parse_hora(settings.escritorio_desde),
        hasta=parse_hora(settings.escritorio_hasta),
        programar=lambda segundos, accion: loop.call_later(segundos, accion),
        reconocedor=cargar_reconocedor(settings.escritorio_modelo_voz)
        if settings.escritorio_oye_azul
        else None,
    )
    parlante.iniciar()
    microfono = Microfono(loop, microfono_cola)
    microfono.iniciar()
    atajo = keyboard.GlobalHotKeys(
        {settings.escritorio_atajo: lambda: loop.call_soon_threadsafe(cliente.atajo)}
    )
    atajo.start()
    log.info(
        "Cliente de escritorio listo. Atajo: %s. Oye Azul: %s (%s–%s).",
        settings.escritorio_atajo,
        "sí" if settings.escritorio_oye_azul else "no",
        settings.escritorio_desde,
        settings.escritorio_hasta,
    )

    async def pasar_microfono() -> None:
        while True:
            cliente.bloque_de_microfono(await microfono_cola.get())

    espera = 1.0
    tarea_microfono = asyncio.create_task(pasar_microfono())
    try:
        while True:
            try:
                async with connect(url, max_size=None) as socket:
                    log.info("Conectado con el núcleo de Azul")
                    espera = 1.0
                    await _sesion(socket, cliente, salida)
            except (OSError, WebSocketException) as error:
                log.info("Sin conexión con el núcleo (%s); reintento en %.0f s", error, espera)
            # Si se cortó a mitad de algo, se parte de cero al reconectar.
            cliente.escuchando = cliente.respondiendo = cliente.esperando_fragmento = False
            cliente.en_conversacion = False
            await asyncio.sleep(espera)
            espera = min(REINTENTO_MAXIMO, espera * 2)
    finally:
        tarea_microfono.cancel()
        atajo.stop()
        microfono.cerrar()
        parlante.cerrar()


async def _sesion(socket, cliente: ClienteEscritorio, salida: asyncio.Queue[str | bytes]) -> None:
    # Lo pendiente de una conexión anterior ya no sirve.
    while not salida.empty():
        salida.get_nowait()

    async def enviar() -> None:
        while True:
            await socket.send(await salida.get())

    tarea_envio = asyncio.create_task(enviar())
    try:
        async for mensaje in socket:
            cliente.mensaje(mensaje)
    finally:
        tarea_envio.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarea_envio


def main() -> None:
    settings = get_settings()
    archivo = settings.data_dir / "escritorio.log"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(archivo, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    if not settings.escritorio_activo:
        log.info("Cliente de escritorio desactivado (AZUL_ESCRITORIO_ACTIVO=false)")
        return
    try:
        asyncio.run(ejecutar())
    except Exception:
        log.exception("El cliente de escritorio se detuvo por un error")
        raise


if __name__ == "__main__":
    main()
