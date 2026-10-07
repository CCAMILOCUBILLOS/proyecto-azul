from datetime import UTC, datetime, timedelta

import pytest

from azul.adapters.sqlite_store import SqliteStore
from azul.core.bandeja import RevisorDeCorreo
from azul.core.ports import Fact, Usage

pytestmark = pytest.mark.anyio

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


class OutlookFalso:
    def __init__(self, correos):
        self.correos = correos
        self.categorias = {}
        self.pedidos = []

    async def nuevos(self, desde, maximo):
        self.pedidos.append(desde)
        return list(self.correos)

    async def categorizar(self, prioridades):
        self.categorias.update(prioridades)


class CerebroClasificador:
    """Clasifica como le digan, llamando a la herramienta igual que Claude."""

    def __init__(self, decisiones):
        self.decisiones = decisiones
        self.solicitudes = []

    async def respond(self, request):
        self.solicitudes.append(request)
        [registrar] = request.tools
        await registrar.handler({"correos": self.decisiones})
        yield Usage("anthropic", 0.002, "clasificación")

    async def prewarm(self, request):
        return None


def correo(n, de="IPS Cali", asunto="Factura vencida"):
    return {
        "id": f"ID{n}",
        "de": de,
        "correo": "x@ips.co",
        "asunto": asunto,
        "fecha": "2026-10-07 09:00",
        "vista": "Le recordamos…",
    }


def decision(n, prioridad, accion="", fecha="", pregunta=""):
    return {
        "n": n,
        "prioridad": prioridad,
        "accion": accion,
        "fecha_limite": fecha,
        "pregunta": pregunta,
    }


@pytest.fixture
def store(tmp_path):
    return SqliteStore(tmp_path / "azul.db")


def revisor(store, correos, decisiones, avisos=None):
    outlook = OutlookFalso(correos)
    cerebro = CerebroClasificador(decisiones)

    async def avisar(texto, voz):
        avisos.append((texto, voz))

    r = RevisorDeCorreo(
        outlook,
        cerebro,
        store,
        store,
        store,
        monthly_budget_usd=30,
        avisar=avisar if avisos is not None else None,
        now=lambda: AHORA,
    )
    return r, outlook, cerebro


async def test_new_mail_is_classified_categorized_and_urgent_alerted_with_voice(store):
    avisos = []
    r, outlook, _ = revisor(
        store,
        [correo(1), correo(2, "Boletín", "Ofertas")],
        [decision(1, "urgente", "Pagar la factura", "2026-10-08"), decision(2, "baja")],
        avisos,
    )

    assert await r.revisar() == 2

    assert outlook.categorias == {"ID1": "urgente", "ID2": "baja"}
    [(texto, voz)] = avisos
    assert "urgente de IPS Cali" in texto and "Pagar la factura" in texto
    assert voz.startswith("Te llegó un correo urgente de IPS Cali")
    itinerario = await store.bandeja_itinerario(10)
    assert [i["asunto"] for i in itinerario] == ["Factura vencida"]  # lo bajo no estorba
    assert itinerario[0]["fecha_limite"] == "2026-10-08"


async def test_mail_is_classified_only_once(store):
    r, _, cerebro = revisor(store, [correo(1)], [decision(1, "alta")])

    await r.revisar()
    await r.revisar()

    assert len(cerebro.solicitudes) == 1


async def test_after_a_long_shutdown_it_only_looks_back_one_day(store):
    r, outlook, _ = revisor(store, [], [])
    await store.bandeja_guardar_estado("ultima_revision", (AHORA - timedelta(days=5)).isoformat())

    await r.revisar()

    assert outlook.pedidos[0] >= AHORA - timedelta(hours=24, minutes=5)


async def test_the_users_rules_and_facts_guide_the_classification(store):
    await store.bandeja_agregar_regla("IPS de Cali sobre facturación", "urgente")
    await store.add_fact(Fact("Trabaja en Red Nacional de Optometría."))
    r, _, cerebro = revisor(store, [correo(1)], [decision(1, "urgente")])

    await r.revisar()

    sistema = cerebro.solicitudes[0].system
    assert "- IPS de Cali sobre facturación → urgente" in sistema
    assert "Red Nacional de Optometría" in sistema
    assert "[1] De: IPS Cali" in cerebro.solicitudes[0].messages[0].text
    assert "ID1" not in cerebro.solicitudes[0].messages[0].text  # ids cortos, no los de Outlook


async def test_doubts_become_questions_and_an_answer_becomes_a_rule(store):
    avisos = []
    r, outlook, _ = revisor(
        store,
        [correo(1)],
        [decision(1, "normal", pregunta="¿Qué tan importantes son las facturas de la IPS?")],
        avisos,
    )
    await r.revisar()

    assert "📬" in avisos[0][0] and avisos[0][1] == ""  # sin nota de voz: no es urgente
    assert "pregunta #1" in await r.contexto()

    herramientas = {h.name: h for h in r.herramientas()}
    resultado = await herramientas["correo_prioridad"].handler(
        {"pregunta": 1, "criterio": "Facturas de la IPS de Cali", "prioridad": "alta"}
    )

    assert "Aprendido" in resultado
    assert outlook.categorias["ID1"] == "alta"
    assert await r.contexto() == ""
    assert (await store.bandeja_reglas())[0]["criterio"] == "Facturas de la IPS de Cali"


async def test_the_initial_review_classifies_without_alerting_and_proposes(store):
    avisos = []
    r, _, _ = revisor(
        store,
        [correo(1), correo(2, "Jefe", "Informe")],
        [decision(1, "urgente"), decision(2, "alta", pregunta="¿El jefe siempre es alta?")],
        avisos,
    )

    resumen = await r.repaso_inicial()

    assert avisos == []
    assert '"IPS Cali": {"urgente": 1}' in resumen
    assert "¿El jefe siempre es alta?" in resumen


async def test_itinerary_items_can_be_marked_done(store):
    r, _, _ = revisor(store, [correo(1)], [decision(1, "alta", "Responder")])
    await r.revisar()
    herramientas = {h.name: h for h in r.herramientas()}
    [item] = await store.bandeja_itinerario(10)

    await herramientas["correo_hecho"].handler({"numero": item["numero"]})

    assert await store.bandeja_itinerario(10) == []


async def test_nothing_is_classified_when_the_monthly_budget_is_spent(store):
    await store.record(Usage("anthropic", 31.0))
    r, _, cerebro = revisor(store, [correo(1)], [decision(1, "alta")])

    assert await r.revisar() == 0
    assert cerebro.solicitudes == []
