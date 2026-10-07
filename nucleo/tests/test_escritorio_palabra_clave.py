from datetime import time

import pytest

from azul.escritorio.horario import dentro_del_horario
from azul.escritorio.palabra_clave import es_llamado


@pytest.mark.parametrize(
    "texto",
    [
        "oye azul",
        "oye azul qué hora es",
        "azul qué hora es",
        "hey azul pon música",
        # Así confunde Vosk "oye" y "oiga" a veces:
        "hoy azul qué hora es",
        "voy azul",
        "ella azul pon música",
        "voy a azul",
        "oye soul qué hora es",
        "hoy azules",
    ],
)
def test_recognizes_calls_to_azul(texto):
    assert es_llamado(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "el cielo está muy azul hoy",
        "voy a comprar un carro azul",
        "un carro azul",
        "oye mira esto",
        "oye y el azúcar",
        "hola cómo estás",
        "",
        "azules",
        "oye solo quería decirte",
        "soul music",
    ],
)
def test_ignores_other_speech(texto):
    assert not es_llamado(texto)


def test_same_start_and_end_means_all_day():
    assert dentro_del_horario(time(3, 0), time(0, 0), time(0, 0))
    assert dentro_del_horario(time(23, 59), time(0, 0), time(0, 0))
    assert not dentro_del_horario(time(23, 0), time(7, 0), time(22, 0))
