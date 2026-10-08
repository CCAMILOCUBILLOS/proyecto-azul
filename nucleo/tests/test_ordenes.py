from datetime import date, datetime

import pytest

from azul.adapters.sqlite_store import SqliteStore
from azul.core.conversation import Conversation, TextChunk
from azul.core.ordenes import RecepcionDeOrdenes, fechas, normalizar
from azul.core.ports import RedNacionalError, ToolSpec, Usage
from tests.fakes import FakeBrain

pytestmark = pytest.mark.anyio

AHORA = datetime(2026, 10, 7, 9, 30)
HOY = AHORA.date()


class TableroFalso:
    def __init__(self, resumen=None, progreso=None, falla=False):
        self.lanzados = []
        self.resumen = resumen or {"pendientes": 6, "ya_creadas": 4, "ultima_orden": "40660"}
        self.progreso = progreso or {}
        self.falla = falla

    async def consultar(self, seccion, parametros):
        if self.falla:
            raise RedNacionalError("No encuentro el tablero de Red Nacional.")
        return self.resumen if seccion == "resumen" else self.progreso

    async def ejecutar(self, operacion, datos):
        self.lanzados.append((operacion, datos))
        return {"ok": True}


@pytest.fixture
def store(tmp_path):
    return SqliteStore(tmp_path / "azul.db")


def recepcion(store, tablero=None, itinerario=None, ahora=AHORA):
    return RecepcionDeOrdenes(
        tablero or TableroFalso(), store, itinerario=itinerario, now=lambda: ahora
    )


# --- Reconocer ---


def test_text_is_normalized_without_the_wake_phrase_or_politeness():
    assert normalizar("Oye Azul, ¿cómo va el CARGUE?, por favor") == "como va el cargue"


@pytest.mark.parametrize(
    ("resto", "esperado"),
    [
        ("", (HOY, HOY)),
        ("de hoy", (HOY, HOY)),
        ("de ayer", (date(2026, 10, 6), date(2026, 10, 6))),
        ("del 2 de octubre", (date(2026, 10, 2), date(2026, 10, 2))),
        ("desde el 2 hasta el 5", (date(2026, 10, 2), date(2026, 10, 5))),
        ("del 28", (date(2026, 9, 28), date(2026, 9, 28))),  # el 28 que ya pasó
        ("de esta semana", (date(2026, 10, 5), HOY)),
        ("pero solo los de wayuuriba", None),
        ("de la semana pasada", None),
    ],
)
def test_dates_are_understood_and_anything_else_is_left_to_claude(resto, esperado):
    assert fechas(resto, HOY) == esperado


async def test_a_known_order_runs_without_claude(store):
    tablero = TableroFalso()

    respuesta = await recepcion(store, tablero).atender("Oye Azul, corre el agendamiento de ayer")

    assert tablero.lanzados == [("agendar", {"desde": "2026-10-06", "hasta": "2026-10-06"})]
    assert respuesta.startswith("Listo, lancé el agendamiento de ayer.")


@pytest.mark.parametrize(
    "frase",
    [
        "¿Ya corriste el agendamiento?",
        "haz los agendamientos pero solo los de Wayuuriba",
        "explícame por qué no cargó Andrea",
        "corre el agendamiento de la semana pasada",
    ],
)
async def test_questions_and_orders_with_extras_go_to_claude(store, frase):
    tablero = TableroFalso()

    assert await recepcion(store, tablero).atender(frase) is None
    assert tablero.lanzados == []


async def test_the_real_upload_asks_first_and_only_runs_with_a_yes(store):
    tablero = TableroFalso()
    r = recepcion(store, tablero)

    pregunta = await r.atender("haz el cargue")
    assert "Hay 6 órdenes pendientes" in pregunta and "¿Hago el cargue real?" in pregunta
    assert tablero.lanzados == []

    assert (await r.atender("Sí")).startswith("Listo, lancé el cargue real")
    assert tablero.lanzados == [("cargue", {"confirmacion": 6})]


async def test_a_no_or_something_else_cancels_the_upload(store):
    tablero = TableroFalso()
    r = recepcion(store, tablero)

    await r.atender("carga las órdenes en Biofile")
    assert await r.atender("no") == "Listo, no lo hago."
    await r.atender("haz el cargue")
    assert await r.atender("¿qué hora es?") is None  # otra cosa: pasa a Claude
    assert await r.atender("sí") is None  # y el "sí" ya no carga nada
    assert tablero.lanzados == []


async def test_the_summary_and_progress_are_spoken_from_the_board(store):
    tablero = TableroFalso(
        progreso={
            "corriendo": True,
            "etiqueta": "Agendamiento",
            "segundos": 125,
            "lineas": ["inicio", "Borrador 3 de 7: IPS Cali", ""],
        }
    )
    r = recepcion(store, tablero)

    resumen = await r.atender("¿Cuántas órdenes hay pendientes?")
    progreso = await r.atender("¿Cómo va?")

    assert resumen.startswith("Hay 6 órdenes pendientes por cargar y 4 ya creadas")
    assert "La última orden creada fue la 40660" in resumen
    assert progreso == (
        "Agendamiento sigue corriendo, lleva 2 minutos. Lo último que dijo: "
        "Borrador 3 de 7: IPS Cali"
    )


async def test_a_board_that_does_not_answer_is_explained(store):
    respuesta = await recepcion(store, TableroFalso(falla=True)).atender("¿Cómo va?")

    assert "No encuentro el tablero" in respuesta


async def test_the_mail_itinerary_is_read_without_claude(store):
    async def itinerario():
        return [
            {"prioridad": "urgente", "de": "IPS Cali", "asunto": "Factura", "accion": "Pagar"},
            {"prioridad": "alta", "de": "Jefe", "asunto": "Informe", "accion": ""},
        ]

    respuesta = await recepcion(store, itinerario=itinerario).atender("¿Qué tengo pendiente?")

    assert respuesta == (
        "Tienes 2 pendientes en el correo. Lo primero: urgente: IPS Cali, Factura (Pagar); "
        "alta: Jefe, Informe."
    )


async def test_without_red_nacional_its_orders_go_to_claude(store):
    r = RecepcionDeOrdenes(None, store, now=lambda: AHORA)

    assert await r.atender("corre el agendamiento") is None


# --- Atajos aprendidos ---


async def test_a_short_order_resolved_by_claude_becomes_a_shortcut_with_relative_dates(store):
    hoy = recepcion(store)
    await hoy.aprender(
        "Azul, organiza lo de red nacional",
        [
            (
                "red_nacional_ejecutar",
                {"operacion": "agendar", "desde": "2026-10-07", "hasta": "2026-10-07"},
            )
        ],
    )
    tablero = TableroFalso()
    manana = recepcion(store, tablero, ahora=datetime(2026, 10, 8, 8, 0))

    respuesta = await manana.atender("organiza lo de red nacional")

    assert tablero.lanzados == [("agendar", {"desde": "2026-10-08", "hasta": "2026-10-08"})]
    assert respuesta.startswith("Listo, lancé el agendamiento de hoy.")


@pytest.mark.parametrize(
    "llamadas",
    [
        [("red_nacional_ejecutar", {"operacion": "cargue"})],  # crea órdenes: nunca atajo
        [("red_nacional_consultar", {"seccion": "clientes"})],  # sin respuesta fija
        [
            ("red_nacional_consultar", {"seccion": "resumen"}),
            ("red_nacional_ejecutar", {"operacion": "agendar"}),
        ],  # dos programas: no es una orden simple
        [("red_nacional_ejecutar", {"operacion": "agendar", "desde": "2026-09-01"})],
    ],
)
async def test_risky_or_complex_requests_are_not_learned(store, llamadas):
    r = recepcion(store)

    await r.aprender("prepara todo", llamadas)

    assert await store.atajo_buscar("prepara todo") is None


# --- Dentro de la conversación ---


async def test_direct_orders_skip_the_brain_but_stay_in_the_history(store):
    brain = FakeBrain(["no debería hablar"])
    tablero = TableroFalso()
    conversacion = Conversation(
        brain,
        memory=store,
        meter=store,
        monthly_budget_usd=50,
        budget_warning_usd=40,
        recepcion=recepcion(store, tablero),
    )

    eventos = [e async for e in conversacion.reply("corre el agendamiento")]

    assert brain.requests == []
    assert [e.text for e in eventos if isinstance(e, TextChunk)][0].startswith("Listo, lancé")
    historial = await store.recent_messages(5)
    assert [m.role for m in historial] == ["user", "assistant"]
    assert historial[-1].consulted == "orden directa"


class CerebroQueUsaUnaHerramienta:
    def __init__(self, nombre, entrada):
        self.nombre, self.entrada = nombre, entrada
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        [tool] = [t for t in request.tools if t.name == self.nombre]
        await tool.handler(self.entrada)
        yield "Listo, lo lancé."
        yield Usage("anthropic", 0.01)

    async def prewarm(self, request):
        return None


async def test_the_conversation_learns_from_what_claude_did(store):
    entrada = {"operacion": "reporte"}
    brain = CerebroQueUsaUnaHerramienta("red_nacional_ejecutar", entrada)

    async def ejecutar(_):
        return '{"ok": true}'

    conversacion = Conversation(
        brain,
        memory=store,
        meter=store,
        monthly_budget_usd=50,
        budget_warning_usd=40,
        herramientas_extra=[ToolSpec("red_nacional_ejecutar", "", {}, ejecutar)],
        recepcion=recepcion(store),
    )

    [_ async for _ in conversacion.reply("saca el informe mensual")]

    assert await store.atajo_buscar("saca el informe mensual") == ("red_nacional_ejecutar", entrada)
