import json

import httpx2
import pytest

from azul.adapters.sqlite_store import SqliteStore
from azul.adapters.tablero_red_nacional import NO_RESPONDE, TableroRedNacional
from azul.core.conversation import Conversation
from azul.core.ports import RedNacionalError
from azul.core.red_nacional import MAX_RESULT_CHARS, herramientas_red_nacional
from tests.fakes import FakeBrain

pytestmark = pytest.mark.anyio


class FakeTablero:
    def __init__(self, pendientes=12, error=None, respuesta=None):
        self.pendientes = pendientes
        self.error = error
        self.respuesta = respuesta
        self.consultas = []
        self.ejecuciones = []

    async def consultar(self, seccion, parametros):
        self.consultas.append((seccion, parametros))
        if self.error:
            raise RedNacionalError(self.error)
        if self.respuesta is not None:
            return self.respuesta
        return {"pendientes": self.pendientes, "creadas_historico": 340}

    async def ejecutar(self, operacion, datos):
        self.ejecuciones.append((operacion, datos))
        if self.error:
            raise RedNacionalError(self.error)
        return {"ok": True, "motivo": ""}


def herramientas(tablero):
    anotado = []
    consultar, ejecutar = herramientas_red_nacional(tablero, anotado.append)
    return consultar, ejecutar, anotado


# --- Herramientas (núcleo) ---


async def test_consultar_returns_the_dashboard_data_and_records_it():
    tablero = FakeTablero()
    consultar, _, anotado = herramientas(tablero)

    resultado = await consultar.handler({"seccion": "resumen"})

    assert json.loads(resultado)["pendientes"] == 12
    assert tablero.consultas == [("resumen", {})]
    assert anotado == ["red nacional: resumen"]


async def test_consultar_passes_only_the_client_fields():
    tablero = FakeTablero()
    consultar, _, _ = herramientas(tablero)

    await consultar.handler({"seccion": "cliente_cargo", "clave": "AVANT", "cargo": "Conductor"})

    assert tablero.consultas == [("cliente_cargo", {"clave": "AVANT", "cargo": "Conductor"})]


async def test_unknown_section_is_an_error_for_the_brain():
    consultar, _, _ = herramientas(FakeTablero())

    with pytest.raises(ValueError):
        await consultar.handler({"seccion": "contraseñas"})


async def test_cargue_sends_the_exact_count_the_dashboard_asks_for():
    # El tablero solo lanza el cargue real si se le dice cuántas órdenes va a crear.
    tablero = FakeTablero(pendientes=12)
    _, ejecutar, anotado = herramientas(tablero)

    await ejecutar.handler({"operacion": "cargue"})
    await ejecutar.handler({"operacion": "cargue", "maximo": 5})

    assert tablero.ejecuciones == [
        ("cargue", {"confirmacion": 12}),
        ("cargue", {"maximo": 5, "confirmacion": 5}),
    ]
    assert anotado == ["red nacional: cargue", "red nacional: cargue"]


async def test_launch_passes_dates_and_drops_empty_fields():
    tablero = FakeTablero()
    _, ejecutar, _ = herramientas(tablero)

    await ejecutar.handler(
        {"operacion": "agendar", "desde": "2026-10-06", "hasta": "2026-10-06", "id": ""}
    )

    assert tablero.ejecuciones == [("agendar", {"desde": "2026-10-06", "hasta": "2026-10-06"})]


async def test_dashboard_problems_are_explained_not_raised():
    _, ejecutar, anotado = herramientas(FakeTablero(error=NO_RESPONDE))

    with pytest.raises(ValueError, match="Tablero.bat"):
        await ejecutar.handler({"operacion": "simulacion"})
    assert anotado == []


async def test_long_answers_are_trimmed():
    tablero = FakeTablero(respuesta={"filas": ["x" * 100] * 500})
    consultar, _, _ = herramientas(tablero)

    resultado = await consultar.handler({"seccion": "seguimiento"})

    assert len(resultado) < MAX_RESULT_CHARS + 100
    assert resultado.endswith("pide algo más puntual si falta)")


async def test_conversation_offers_the_tools_and_marks_what_was_consulted(tmp_path):
    store = SqliteStore(tmp_path / "azul.db")

    class AnswersFromTheDashboard(FakeBrain):
        async def respond(self, request):
            self.requests.append(request)
            tool = next(t for t in request.tools if t.name == "red_nacional_consultar")
            await tool.handler({"seccion": "resumen"})
            yield "Hay 12 pendientes."

    brain = AnswersFromTheDashboard()
    conversation = Conversation(
        brain,
        memory=store,
        meter=store,
        monthly_budget_usd=50,
        budget_warning_usd=40,
        red_nacional=FakeTablero(),
    )
    async for _ in conversation.reply("¿cuántas órdenes faltan?"):
        pass

    assert [t.name for t in brain.requests[0].tools] == [
        "red_nacional_consultar",
        "red_nacional_ejecutar",
    ]
    assert (await store.recent_messages(1))[0].consulted == "red nacional: resumen"


# --- Adaptador HTTP ---


def tablero_simulado(responder):
    pedidos = []

    def manejar(request):
        pedidos.append(request)
        return responder(request)

    cliente = httpx2.AsyncClient(
        base_url="https://optometria.tail.ts.net", transport=httpx2.MockTransport(manejar)
    )
    return TableroRedNacional("https://optometria.tail.ts.net", client=cliente), pedidos


async def test_adapter_reads_the_same_routes_as_the_buttons():
    tablero, pedidos = tablero_simulado(lambda r: httpx2.Response(200, json={"pendientes": 3}))

    assert await tablero.consultar("resumen", {}) == {"pendientes": 3}
    await tablero.consultar("cliente_perfil", {"clave": "AVANT", "cargo": "ignorado"})
    await tablero.consultar("progreso", {})

    assert [str(p.url) for p in pedidos] == [
        "https://optometria.tail.ts.net/api/resumen",
        "https://optometria.tail.ts.net/api/clientes/perfil?clave=AVANT",
        "https://optometria.tail.ts.net/api/log?desde=0",
    ]


async def test_adapter_launches_through_the_generic_button():
    tablero, pedidos = tablero_simulado(lambda r: httpx2.Response(200, json={"ok": True}))

    await tablero.ejecutar("cargue", {"confirmacion": 12, "desde": "no-aplica"})
    await tablero.ejecutar("detener", {})

    assert pedidos[0].url.path == "/api/lanzar"
    assert json.loads(pedidos[0].content) == {"accion": "cargue", "confirmacion": 12}
    # Sin cabecera Origin: el tablero solo rechaza POST de otras páginas web.
    assert "origin" not in pedidos[0].headers
    assert pedidos[1].url.path == "/api/detener"


async def test_adapter_passes_the_dashboard_refusal_through():
    tablero, _ = tablero_simulado(
        lambda r: httpx2.Response(409, json={"ok": False, "motivo": "No hay órdenes pendientes."})
    )

    assert await tablero.ejecutar("cargue", {"confirmacion": 0}) == {
        "ok": False,
        "motivo": "No hay órdenes pendientes.",
    }


async def test_adapter_explains_when_the_dashboard_is_off():
    def apagado(request):
        raise httpx2.ConnectError("sin conexión", request=request)

    tablero, _ = tablero_simulado(apagado)

    with pytest.raises(RedNacionalError, match="PC de Optometría"):
        await tablero.consultar("resumen", {})


def test_only_red_nacional_tools_use_strict_mode():
    from azul.adapters.anthropic_brain import _tool_definition
    from azul.core.red_nacional import herramientas_red_nacional

    for herramienta in herramientas_red_nacional(object(), lambda _: None):
        assert _tool_definition(herramienta)["strict"] is True
