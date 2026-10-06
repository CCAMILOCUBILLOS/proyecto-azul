"""Micrófono y parlantes del portátil con miniaudio (ADR 0028)."""

import array
import asyncio
import math
import threading
from collections.abc import Callable

import miniaudio

TASA_MICROFONO = 16_000  # lo que espera el núcleo: PCM 16 bits mono 16 kHz
TASA_PARLANTE = 24_000
BYTES_POR_BLOQUE = TASA_MICROFONO * 2 // 10  # 0,1 s


class Microfono:
    """Entrega el micrófono en bloques de 0,1 s a una cola de asyncio."""

    def __init__(self, loop: asyncio.AbstractEventLoop, cola: asyncio.Queue[bytes]) -> None:
        self._loop = loop
        self._cola = cola
        self._dispositivo: miniaudio.CaptureDevice | None = None
        self._pendiente = bytearray()

    def iniciar(self) -> None:
        self._dispositivo = miniaudio.CaptureDevice(
            input_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=TASA_MICROFONO,
            buffersize_msec=100,
            app_name="Azul",
        )
        generador = self._recibir()
        next(generador)
        self._dispositivo.start(generador)

    def cerrar(self) -> None:
        if self._dispositivo:
            self._dispositivo.close()

    def _recibir(self):
        # Corre en el hilo de audio: se reagrupa en bloques exactos y se pasan a asyncio.
        while True:
            datos = yield
            self._pendiente.extend(datos)
            while len(self._pendiente) >= BYTES_POR_BLOQUE:
                bloque = bytes(self._pendiente[:BYTES_POR_BLOQUE])
                del self._pendiente[:BYTES_POR_BLOQUE]
                self._loop.call_soon_threadsafe(self._cola.put_nowait, bloque)


class Parlante:
    """Reproduce las frases de Azul (MP3) en orden, y tonos cortos de aviso."""

    def __init__(self, al_terminar: Callable[[], None] | None = None) -> None:
        self._al_terminar = al_terminar
        self._buffer = bytearray()
        self._candado = threading.Lock()
        self._sonando = False
        self._dispositivo: miniaudio.PlaybackDevice | None = None

    @property
    def sonando(self) -> bool:
        return self._sonando

    def iniciar(self) -> None:
        self._dispositivo = miniaudio.PlaybackDevice(
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=TASA_PARLANTE,
            buffersize_msec=100,
            app_name="Azul",
        )
        generador = self._alimentar()
        next(generador)
        self._dispositivo.start(generador)

    def cerrar(self) -> None:
        if self._dispositivo:
            self._dispositivo.close()

    def reproducir_mp3(self, mp3: bytes) -> None:
        sonido = miniaudio.decode(
            mp3,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=TASA_PARLANTE,
        )
        self._agregar(sonido.samples.tobytes())

    def tono(self, frecuencia: float = 880, milisegundos: int = 150) -> None:
        self._agregar(tono_pcm(frecuencia, milisegundos))

    def detener(self) -> None:
        with self._candado:
            self._buffer.clear()
            self._sonando = False

    def _agregar(self, pcm: bytes) -> None:
        with self._candado:
            self._buffer.extend(pcm)
            self._sonando = True

    def _alimentar(self):
        # Corre en el hilo de audio: entrega lo pedido o silencio si no hay nada.
        cuadros = yield b""
        while True:
            pedido = cuadros * 2
            terminado = False
            with self._candado:
                trozo = bytes(self._buffer[:pedido])
                del self._buffer[:pedido]
                if self._sonando and not self._buffer:
                    self._sonando = False
                    terminado = True
            if terminado and self._al_terminar:
                self._al_terminar()
            cuadros = yield trozo + bytes(pedido - len(trozo))


def tono_pcm(frecuencia: float, milisegundos: int, tasa: int = TASA_PARLANTE) -> bytes:
    """Un tono suave (con entrada y salida graduales) en PCM de 16 bits."""
    total = tasa * milisegundos // 1000
    rampa = max(1, total // 10)
    muestras = array.array("h")
    for i in range(total):
        envolvente = min(1.0, i / rampa, (total - i) / rampa)
        muestras.append(int(6000 * envolvente * math.sin(2 * math.pi * frecuencia * i / tasa)))
    return muestras.tobytes()
