""" "Oye Azul" reconocido en el propio portátil, sin internet (ADR 0035).

Usa Vosk con su modelo pequeño de español y vocabulario completo: con un
vocabulario reducido a "oye azul" confundía casi cualquier frase con el
llamado. Solo recibe audio cuando el detector de voz oye a alguien hablar, así
que en silencio no gasta procesador. Lo que se dice antes de "Oye Azul" nunca
sale del equipo.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

TASA = 16_000
ALTERNATIVAS = 3
# Palabras que suelen ir antes de "azul" al llamarla (y cómo las confunde Vosk:
# "oye" a veces sale como "hoy", "voy" o "ella"; "oiga azul", como "voy a azul").
_ANTES = {"oye", "oyes", "oiga", "hey", "ey", "hoy", "voy", "ella", "oí", "oigo", "a", "y", "o"}
_LLAMADOS = {"oye", "oyes", "oiga", "hey", "ey", "hoy"}
# Cómo oye a veces "azul" el modelo pequeño; solo cuentan justo después de un llamado
# ("oye soul"), nunca solas, para no confundirlas con palabras comunes.
_COMO_AZUL = {"azules", "soul", "seúl", "asul"}


def es_llamado(texto: str) -> bool:
    """¿La frase empieza llamando a Azul? ("oye azul…", "azul, …", "hoy azul…").

    "Azul" tiene que estar entre las tres primeras palabras y, si no es la
    primera, solo con palabras de llamado antes: "un carro azul" no cuenta.
    """
    palabras = texto.lower().split()
    for posicion, palabra in enumerate(palabras[:3]):
        if palabra == "azul":
            return all(previa in _ANTES for previa in palabras[:posicion])
        if palabra in _COMO_AZUL and posicion > 0 and palabras[posicion - 1] in _LLAMADOS:
            return all(previa in _ANTES for previa in palabras[:posicion])
    return False


class ReconocedorLocal:
    def __init__(self, carpeta_modelo: Path) -> None:
        import vosk  # solo se carga si el modelo existe

        vosk.SetLogLevel(-1)
        self._modelo = vosk.Model(str(carpeta_modelo))
        self._crear = self._nuevo
        self._vosk = vosk
        self._reconocedor = self._crear()

    def _nuevo(self):  # type: ignore[no-untyped-def]
        reconocedor = self._vosk.KaldiRecognizer(self._modelo, TASA)
        # Al cerrar una frase se miran las tres lecturas más probables, no solo la primera.
        reconocedor.SetMaxAlternatives(ALTERNATIVAS)
        return reconocedor

    def reiniciar(self) -> None:
        self._reconocedor = self._crear()

    def cerrar(self) -> bool:
        """La frase terminó: revisa sus lecturas completas (más fiables que las parciales)."""
        resultado = json.loads(self._reconocedor.FinalResult())
        lecturas = [a.get("text", "") for a in resultado.get("alternatives", [])]
        return any(es_llamado(lectura) for lectura in lecturas)

    def escuchar(self, bloque: bytes) -> bool:
        """Agrega 0,1 s de audio; True si lo oído hasta ahora es un llamado a Azul."""
        if self._reconocedor.AcceptWaveform(bloque):
            resultado = json.loads(self._reconocedor.Result())
            lecturas = [a.get("text", "") for a in resultado.get("alternatives", [])]
            return any(es_llamado(lectura) for lectura in lecturas)
        return es_llamado(json.loads(self._reconocedor.PartialResult()).get("partial", ""))


def cargar_reconocedor(carpeta_modelo: Path) -> ReconocedorLocal | None:
    """El reconocedor local, o None si falta el modelo o la librería (se usa Deepgram)."""
    if not carpeta_modelo.is_dir():
        log.info("Sin modelo local de voz en %s: 'Oye Azul' usará Deepgram", carpeta_modelo)
        return None
    try:
        return ReconocedorLocal(carpeta_modelo)
    except Exception:
        log.exception("No se pudo cargar el modelo local de voz; 'Oye Azul' usará Deepgram")
        return None
