import array
from datetime import time

import pytest

from azul.escritorio.deteccion import DetectorDeVoz, volumen
from azul.escritorio.horario import dentro_del_horario, parse_hora

MUESTRAS_POR_BLOQUE = 1600  # 0,1 s a 16 kHz


def bloque(amplitud: int) -> bytes:
    # Onda cuadrada: su volumen es exactamente amplitud/32768.
    return array.array("h", [amplitud, -amplitud] * (MUESTRAS_POR_BLOQUE // 2)).tobytes()


SILENCIO = bloque(20)  # ~0,0006
VOZ = bloque(3000)  # ~0,09


class Registro:
    def __init__(self):
        self.eventos = []

    def detector(self):
        return DetectorDeVoz(
            empezar=lambda previos: self.eventos.append(("empezar", len(previos))),
            audio=lambda b: self.eventos.append(("audio",)),
            terminar=lambda: self.eventos.append(("terminar",)),
        )


def test_volumen():
    assert volumen(VOZ) == pytest.approx(3000 / 32768)
    assert volumen(b"") == 0.0


def test_detects_a_voice_fragment_with_previous_audio_and_ends_on_silence():
    registro = Registro()
    detector = registro.detector()

    for _ in range(10):
        detector.agregar(SILENCIO, puede_empezar=True)
    for _ in range(5):
        detector.agregar(VOZ, puede_empezar=True)
    for _ in range(12):
        detector.agregar(SILENCIO, puede_empezar=True)

    assert registro.eventos[0] == ("empezar", 5)  # 0,5 s previos para no cortar el "Oye"
    assert registro.eventos.count(("audio",)) == 3 + 12
    assert registro.eventos[-1] == ("terminar",)
    assert not detector.en_fragmento


def test_does_not_start_while_azul_is_busy():
    registro = Registro()
    detector = registro.detector()

    for _ in range(10):
        detector.agregar(VOZ, puede_empezar=False)

    assert registro.eventos == []


def test_ignores_a_single_noise_blip():
    registro = Registro()
    detector = registro.detector()

    for muestra in [SILENCIO, VOZ, SILENCIO, SILENCIO]:
        detector.agregar(muestra, puede_empezar=True)

    assert registro.eventos == []


@pytest.mark.parametrize(
    ("ahora", "desde", "hasta", "esperado"),
    [
        ("08:00", "07:00", "22:00", True),
        ("06:59", "07:00", "22:00", False),
        ("22:00", "07:00", "22:00", False),
        ("23:30", "22:00", "02:00", True),
        ("01:00", "22:00", "02:00", True),
        ("12:00", "22:00", "02:00", False),
    ],
)
def test_horario(ahora, desde, hasta, esperado):
    assert dentro_del_horario(parse_hora(ahora), parse_hora(desde), parse_hora(hasta)) is esperado


def test_parse_hora():
    assert parse_hora("7:05") == time(7, 5)
    assert parse_hora(" 22 ") == time(22, 0)
