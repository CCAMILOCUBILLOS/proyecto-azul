"""Verificación de voz con Vosk: ¿quien habla es el usuario? (ADR 0036).

Cada voz se resume en un vector de 128 números (x-vector) con el modelo de
hablantes de Vosk. La "huella" del usuario es el promedio de sus muestras de
inscripción; la de Azul, el de unas frases de su propia voz (Gloria). Se acepta
una voz si se parece lo bastante al usuario y bastante más al usuario que a
Azul: así Azul no se interrumpe con su propio eco.

Todo ocurre en el portátil. Se guarda solo la huella numérica, nunca el audio.
"""

import asyncio
import json
import logging
import math
from collections.abc import Awaitable, Callable
from pathlib import Path

log = logging.getLogger(__name__)

TASA = 16_000
BYTES_POR_SEGUNDO = TASA * 2
# Con menos voz que esto, la huella no es confiable.
MINIMO_SEGUNDOS = 0.6
# Calibrado con voces de prueba (ADR 0036), con 2 s o más de voz: el mismo hablante da
# 0,52–0,77, otro hombre 0,38–0,43 y la voz de Azul 0,11–0,24; con eco de Azul encima,
# la huella se parece más a Azul.
UMBRAL = 0.48
MARGEN_SOBRE_AZUL = 0.15
# Entre este valor y el umbral, la respuesta es "dudoso": conviene oír más voz.
UMBRAL_DE_DUDA = 0.33


class VerificadorVosk:
    def __init__(
        self,
        modelo_voz: Path,
        modelo_hablantes: Path,
        archivo_huella: Path,
        archivo_huella_azul: Path,
        voz_de_azul: Callable[[], Awaitable[list[bytes]]] | None = None,
    ) -> None:
        self._modelo_voz = modelo_voz
        self._modelo_hablantes = modelo_hablantes
        self._archivo = archivo_huella
        self._archivo_azul = archivo_huella_azul
        self._voz_de_azul = voz_de_azul
        self._modelos = None
        self._muestras: list[list[float]] = []
        self._huella = _leer(archivo_huella)
        self._huella_azul = _leer(archivo_huella_azul)
        self._candado = asyncio.Lock()

    @property
    def inscrito(self) -> bool:
        return self._huella is not None

    @property
    def muestras(self) -> int:
        return len(self._muestras)

    async def agregar_muestra(self, pcm: bytes) -> int:
        """Una frase de inscripción. Devuelve cuántas van."""
        vector = await self._vector(pcm)
        if vector is None:
            raise ValueError(
                "No oí suficiente voz en esa muestra. Intenta de nuevo, un poco más fuerte."
            )
        self._muestras.append(vector)
        return len(self._muestras)

    async def terminar_inscripcion(self) -> None:
        if len(self._muestras) < 3:
            raise ValueError("Necesito al menos 3 frases para aprender tu voz.")
        self._huella = _promedio(self._muestras)
        self._muestras = []
        _guardar(self._archivo, self._huella)
        log.info("Huella de voz del usuario guardada")
        await self._preparar_huella_azul()

    async def borrar(self) -> None:
        self._huella = None
        self._muestras = []
        self._archivo.unlink(missing_ok=True)

    async def es_el_usuario(self, pcm: bytes) -> bool:
        return await self.veredicto(pcm) == "si"

    async def veredicto(self, pcm: bytes) -> str:
        """ "si", "no" o "dudoso" (se parece, pero no lo bastante: conviene oír más)."""
        if self._huella is None:
            return "no"
        vector = await self._vector(pcm)
        if vector is None:
            return "no"
        parecido = _coseno(vector, self._huella)
        a_azul = _coseno(vector, self._huella_azul) if self._huella_azul else 0.0
        if parecido - a_azul < MARGEN_SOBRE_AZUL:
            resultado = "no"
        elif parecido >= UMBRAL:
            resultado = "si"
        elif parecido >= UMBRAL_DE_DUDA:
            resultado = "dudoso"
        else:
            resultado = "no"
        # Solo números, nunca lo dicho: sirve para ajustar el umbral.
        log.info("Verificación de voz: usuario %.2f, Azul %.2f → %s", parecido, a_azul, resultado)
        return resultado

    async def _preparar_huella_azul(self) -> None:
        if self._huella_azul is not None or self._voz_de_azul is None:
            return
        try:
            frases = await self._voz_de_azul()
            vectores = [v for v in [await self._vector(pcm) for pcm in frases] if v]
            if vectores:
                self._huella_azul = _promedio(vectores)
                _guardar(self._archivo_azul, self._huella_azul)
        except Exception:
            log.exception("No se pudo preparar la huella de la voz de Azul")

    async def _vector(self, pcm: bytes) -> list[float] | None:
        if len(pcm) < MINIMO_SEGUNDOS * BYTES_POR_SEGUNDO:
            return None
        async with self._candado:
            return await asyncio.to_thread(self._calcular, pcm)

    def _calcular(self, pcm: bytes) -> list[float] | None:
        import vosk

        if self._modelos is None:
            vosk.SetLogLevel(-1)
            self._modelos = (
                vosk.Model(str(self._modelo_voz)),
                vosk.SpkModel(str(self._modelo_hablantes)),
            )
        modelo, hablantes = self._modelos
        reconocedor = vosk.KaldiRecognizer(modelo, TASA)
        reconocedor.SetSpkModel(hablantes)
        vectores: list[list[float]] = []
        for inicio in range(0, len(pcm), 3200):
            if reconocedor.AcceptWaveform(pcm[inicio : inicio + 3200]):
                vector = json.loads(reconocedor.Result()).get("spk")
                if vector:
                    vectores.append(vector)
        final = json.loads(reconocedor.FinalResult()).get("spk")
        if final:
            vectores.append(final)
        return _promedio(vectores) if vectores else None


def cargar_verificador(
    modelo_voz: Path,
    modelo_hablantes: Path,
    carpeta_datos: Path,
    voz_de_azul: Callable[[], Awaitable[list[bytes]]] | None = None,
) -> VerificadorVosk | None:
    """El verificador, o None si faltan los modelos o la librería."""
    if not (modelo_voz.is_dir() and modelo_hablantes.is_dir()):
        log.info("Sin modelos de voz locales: interrumpir con la voz no está disponible")
        return None
    try:
        import vosk  # noqa: F401
    except ImportError:
        log.info("Sin la librería vosk: interrumpir con la voz no está disponible")
        return None
    return VerificadorVosk(
        modelo_voz,
        modelo_hablantes,
        carpeta_datos / "huella_voz.json",
        carpeta_datos / "huella_voz_azul.json",
        voz_de_azul,
    )


def _promedio(vectores: list[list[float]]) -> list[float]:
    return [sum(columna) / len(vectores) for columna in zip(*vectores, strict=True)]


def _coseno(a: list[float], b: list[float]) -> float:
    producto = sum(x * y for x, y in zip(a, b, strict=True))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return producto / norma if norma else 0.0


def _leer(archivo: Path) -> list[float] | None:
    try:
        return [float(v) for v in json.loads(archivo.read_text(encoding="utf-8"))]
    except (OSError, ValueError, TypeError):
        return None


def _guardar(archivo: Path, vector: list[float]) -> None:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(vector), encoding="utf-8")
