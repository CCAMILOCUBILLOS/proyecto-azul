"""Detector de voz local (misma lógica que app/src/deteccion.ts, ADR 0025).

Recibe bloques de 0,1 s de PCM de 16 bits, aprende el ruido de fondo y avisa
cuándo empieza y termina alguien de hablar. Solo esos fragmentos se envían.
"""

import array
import math
from collections import deque
from collections.abc import Callable

BLOQUES_PREVIOS = 5  # 0,5 s antes de detectar la voz
BLOQUES_CON_VOZ_PARA_EMPEZAR = 2  # 0,2 s seguidos de voz
BLOQUES_DE_SILENCIO_PARA_TERMINAR = 12  # 1,2 s de silencio
MAXIMO_BLOQUES = 300  # 30 s por fragmento
VOLUMEN_MINIMO = 0.005
VECES_SOBRE_EL_RUIDO = 3.0


class DetectorDeVoz:
    def __init__(
        self,
        empezar: Callable[[list[bytes]], None],
        audio: Callable[[bytes], None],
        terminar: Callable[[], None],
    ) -> None:
        self._empezar = empezar
        self._audio = audio
        self._terminar = terminar
        self._ruido_de_fondo = 0.002
        self._previos: deque[bytes] = deque(maxlen=BLOQUES_PREVIOS)
        self._bloques_con_voz = 0
        self._en_fragmento = False
        self._silencio = 0
        self._largo = 0
        self._ultimo_fragmento: list[float] = []

    @property
    def en_fragmento(self) -> bool:
        return self._en_fragmento

    def reiniciar(self) -> None:
        self._en_fragmento = False
        self._bloques_con_voz = 0
        self._previos.clear()

    def aprender_ruido(self) -> None:
        """El último fragmento no era voz para Azul: su nivel típico pasa a ser "ruido".

        Así un ventilador o un murmullo constante deja de abrir fragmentos una y otra vez.
        """
        if self._ultimo_fragmento:
            niveles = sorted(self._ultimo_fragmento)
            mediana = niveles[len(niveles) // 2]
            self._ruido_de_fondo = max(self._ruido_de_fondo, mediana)
            self._ultimo_fragmento = []

    def agregar(self, bloque: bytes, puede_empezar: bool) -> None:
        nivel = volumen(bloque)
        umbral = max(VOLUMEN_MINIMO, self._ruido_de_fondo * VECES_SOBRE_EL_RUIDO)
        hay_voz = nivel > umbral
        if self._en_fragmento:
            self._ultimo_fragmento.append(nivel)

        if not self._en_fragmento:
            # Se aprende el ruido de fondo solo cuando nadie habla.
            if not hay_voz:
                self._ruido_de_fondo = self._ruido_de_fondo * 0.95 + nivel * 0.05
            self._previos.append(bloque)
            self._bloques_con_voz = self._bloques_con_voz + 1 if hay_voz else 0
            if self._bloques_con_voz >= BLOQUES_CON_VOZ_PARA_EMPEZAR and puede_empezar:
                self._en_fragmento = True
                self._silencio = 0
                self._largo = 0
                self._ultimo_fragmento = []
                self._empezar(list(self._previos))
                self._previos.clear()
            return

        self._audio(bloque)
        self._largo += 1
        self._silencio = 0 if hay_voz else self._silencio + 1
        if self._silencio >= BLOQUES_DE_SILENCIO_PARA_TERMINAR or self._largo >= MAXIMO_BLOQUES:
            self._en_fragmento = False
            self._bloques_con_voz = 0
            self._terminar()


def volumen(bloque: bytes) -> float:
    """Volumen (RMS) de PCM de 16 bits, entre 0 y 1."""
    muestras = array.array("h", bloque)
    if not muestras:
        return 0.0
    return math.sqrt(sum(m * m for m in muestras) / len(muestras)) / 32768
