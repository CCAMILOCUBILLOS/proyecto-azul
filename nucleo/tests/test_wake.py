import pytest

from azul.core.wake import split_wake_phrase


@pytest.mark.parametrize(
    ("text", "command"),
    [
        ("Oye Azul, ¿qué clima hace?", "¿qué clima hace?"),
        ("¡Oye, Azul! ¿Cómo estás?", "¿Cómo estás?"),
        ("oye azul", ""),
        ("Oye Azul.", ""),
        ("Hey Azul, apaga eso", "apaga eso"),
        ("Óye Azúl, ¿qué día es hoy?", "¿qué día es hoy?"),
        # Formas en que Deepgram suele escribir "Oye Azul".
        ("Hoy, Azul, ¿qué hora es?", "¿qué hora es?"),
        ("Oy Azul cuéntame un chiste", "cuéntame un chiste"),
        ("Okey Azul, gracias", "gracias"),
        ("O Azul, ¿qué tal?", "¿qué tal?"),
        # Llamado directo cuando se perdió el "Oye".
        ("Azul, ¿qué hora es?", "¿qué hora es?"),
        ("Azul.", ""),
        ("Azul", ""),
    ],
)
def test_detects_the_wake_phrase_and_keeps_the_rest(text, command):
    assert split_wake_phrase(text) == command


@pytest.mark.parametrize(
    "text",
    [
        "",
        "El cielo está muy azul hoy",
        "Azul es mi color favorito",
        "Te digo que oye azul es el nombre",
        "Oye Azulejo",
        "Oye, ¿viste el partido?",
        "Hoy hace calor",
        "Hoy azulejamos la cocina",
    ],
)
def test_ignores_everything_else(text):
    assert split_wake_phrase(text) is None
