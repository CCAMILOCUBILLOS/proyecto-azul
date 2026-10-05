import pytest

from azul.core.stop import is_stop_command


@pytest.mark.parametrize(
    "text",
    [
        "Para.",
        "Azul, para",
        "¡Detente!",
        "alto ya",
        "cállate por favor",
        "Ya, basta",
        "Oye, espera",
    ],
)
def test_recognizes_stop_commands(text):
    assert is_stop_command(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "¿Para qué sirve esto?",
        "para eso mejor dime el clima",
        "espera un momento que pienso",
        "hola Azul",
        "para para para para para para",
    ],
)
def test_ignores_normal_phrases(text):
    assert not is_stop_command(text)


@pytest.mark.parametrize(
    "text",
    ["Adiós.", "Chao, Azul", "Gracias, eso es todo.", "Listo, nada más", "Hasta luego, Azul"],
)
def test_farewells_end_the_conversation(text):
    assert is_stop_command(text)


@pytest.mark.parametrize(
    "text",
    ["¿Eso es todo lo que sabes?", "Gracias por la información", "Dime adiós en francés"],
)
def test_phrases_that_only_mention_farewells_are_not_stops(text):
    assert not is_stop_command(text)
