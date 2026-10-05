import pytest

from azul.core.effort import choose_effort
from azul.core.ports import Effort


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hola, ¿cómo vas?", Effort.LOW),
        ("¿va a llover mañana?", Effort.LOW),
        ("¿Por qué el cielo es azul?", Effort.MEDIUM),
        ("Explícame cómo funciona una hipoteca", Effort.MEDIUM),
        ("Analiza a fondo si me conviene cambiar de trabajo", Effort.HIGH),
        ("dime paso a paso cómo preparo una lasaña", Effort.HIGH),
        (
            "ayer estuve pensando en lo que me dijiste sobre el viaje y creo que al final "
            "sí vamos a ir en diciembre con mi familia",
            Effort.MEDIUM,
        ),
    ],
)
def test_choose_effort(text, expected):
    assert choose_effort(text) == expected
