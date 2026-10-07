import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from azul.adapters.sqlite_store import SqliteStore
from azul.adapters.whatsapp_meta import WhatsAppMeta, crear_receptor, mensajes_de
from azul.core.conversation import TextChunk
from azul.core.ports import MensajeEntrante, ToolSpec, WhatsAppError
from azul.core.whatsapp import SIN_PERMISO, Recepcionista

pytestmark = pytest.mark.anyio

DUENO = "573000000001"
PEDRO = "573000000002"


class WhatsAppFalso:
    def __init__(self):
        self.enviados = []
        self.plantillas = []
        self.audios = []

    async def enviar(self, numero, texto):
        self.enviados.append((numero, texto))

    async def enviar_plantilla(self, numero, plantilla):
        self.plantillas.append((numero, plantilla))

    async def enviar_audio(self, numero, mp3):
        self.audios.append((numero, mp3))


class ConversacionFalsa:
    """Responde con un texto fijo; si el mensaje habla de una orden, consulta Red Nacional."""

    def __init__(self, memoria, envolver=None, consultas=None):
        self.memoria = memoria
        self.consultas = consultas if consultas is not None else []
        herramienta = ToolSpec("red_nacional_consultar", "", {}, self._consultar)
        self.herramienta = envolver(herramienta) if envolver else herramienta

    async def _consultar(self, entrada):
        self.consultas.append(entrada)
        return "La orden 40660 está despachada."

    def nombres_de_herramientas(self):
        return ["clima", "red_nacional_consultar", "whatsapp_decidir"]

    async def reply(self, texto):
        await self.memoria.add_message(_mensaje("user", texto))
        if "orden" in texto or "autorizó" in texto:
            resultado = await self.herramienta.handler({"seccion": "seguimiento"})
            respuesta = "Déjame consultarlo." if resultado == SIN_PERMISO else resultado
        else:
            respuesta = f"Respuesta a: {texto}"
        await self.memoria.add_message(_mensaje("assistant", respuesta))
        yield TextChunk(respuesta)


def _mensaje(rol, texto):
    from azul.core.ports import Message

    return Message(rol, texto)


@pytest.fixture
def mundo(tmp_path):
    store = SqliteStore(tmp_path / "azul.db")
    whatsapp = WhatsAppFalso()
    recepcionista = Recepcionista(whatsapp, store, DUENO, plantilla_aviso="aviso_azul")
    consultas = []
    dueno = ConversacionFalsa(store)
    recepcionista.conectar(
        dueno, lambda memoria, envolver, _: ConversacionFalsa(memoria, envolver, consultas)
    )
    return store, whatsapp, recepcionista, consultas


def mensaje(de, texto, id_=None, nombre="Pedro"):
    return MensajeEntrante(
        id=id_ or f"wamid.{de}.{texto}", de=de, nombre=nombre, tipo="text", texto=texto
    )


async def decidir(recepcionista, **entrada):
    herramienta = next(
        h for h in recepcionista.herramientas_del_dueno() if h.name == "whatsapp_decidir"
    )
    return await herramienta.handler(entrada)


async def test_the_users_own_messages_go_to_azul_and_get_an_answer(mundo):
    _, whatsapp, recepcionista, _ = mundo

    await recepcionista.recibir(mensaje(DUENO, "Hola Azul", nombre="Juan"))

    assert whatsapp.enviados == [(DUENO, "Respuesta a: Hola Azul")]


async def test_a_repeated_delivery_is_answered_once(mundo):
    _, whatsapp, recepcionista, _ = mundo

    await recepcionista.recibir(mensaje(DUENO, "Hola", id_="wamid.1"))
    await recepcionista.recibir(mensaje(DUENO, "Hola", id_="wamid.1"))

    assert len(whatsapp.enviados) == 1


async def test_an_unknown_contact_gets_nothing_until_the_user_approves(mundo):
    store, whatsapp, recepcionista, _ = mundo
    await store.wa_guardar_contacto(DUENO, "Juan")  # escribió hace poco: hay ventana

    await recepcionista.recibir(mensaje(PEDRO, "¿Juan está?"))

    [(numero, aviso)] = whatsapp.enviados
    assert numero == DUENO
    assert "Pedro escribió: «¿Juan está?»" in aviso and "Respuesta a: ¿Juan está?" in aviso
    [pendiente] = await store.wa_pendientes()
    assert "#" + str(pendiente.id) in await recepcionista.contexto_para_dueno()

    resultado = await decidir(recepcionista, id=pendiente.id, decision="enviar")

    assert whatsapp.enviados[-1] == (PEDRO, "Respuesta a: ¿Juan está?")
    assert "Pedro" in resultado
    assert await store.wa_pendientes() == []


async def test_remembering_a_reply_rule_makes_azul_answer_alone_next_time(mundo):
    store, whatsapp, recepcionista, _ = mundo
    await store.wa_guardar_contacto(DUENO, "Juan")
    await recepcionista.recibir(mensaje(PEDRO, "Hola"))
    [pendiente] = await store.wa_pendientes()

    await decidir(recepcionista, id=pendiente.id, decision="enviar", recordar="Es de confianza")
    whatsapp.enviados.clear()
    await recepcionista.recibir(mensaje(PEDRO, "¿Cómo vas?"))

    assert whatsapp.enviados == [(PEDRO, "Respuesta a: ¿Cómo vas?")]


async def test_a_correction_is_sent_and_replaces_the_stored_answer(mundo):
    store, whatsapp, recepcionista, _ = mundo
    await store.wa_guardar_contacto(DUENO, "Juan")
    await recepcionista.recibir(mensaje(PEDRO, "Hola"))
    [pendiente] = await store.wa_pendientes()

    await decidir(
        recepcionista, id=pendiente.id, decision="corregir", texto="Hola Pedro, ya te llamo."
    )

    assert whatsapp.enviados[-1] == (PEDRO, "Hola Pedro, ya te llamo.")
    historial = await store.memoria_de(PEDRO).recent_messages(10)
    assert historial[-1].text == "Hola Pedro, ya te llamo."


async def test_tools_need_the_users_permission_and_can_be_learned(mundo):
    store, whatsapp, recepcionista, consultas = mundo
    await store.wa_guardar_contacto(DUENO, "Juan")

    await recepcionista.recibir(mensaje(PEDRO, "¿Cómo va mi orden?"))

    assert consultas == []  # no consultó nada sin permiso
    [(numero, aviso)] = whatsapp.enviados
    assert numero == DUENO and "🔐" in aviso and "Red Nacional: consultas" in aviso
    [pendiente] = await store.wa_pendientes()
    assert pendiente.tipo == "permiso"

    await decidir(
        recepcionista,
        id=pendiente.id,
        decision="permitir",
        recordar="Dale el estado de sus órdenes",
    )

    assert len(consultas) == 1
    assert whatsapp.enviados[-1] == (PEDRO, "La orden 40660 está despachada.")
    whatsapp.enviados.clear()
    await recepcionista.recibir(mensaje(PEDRO, "¿Y la otra orden?"))
    assert len(consultas) == 2  # la regla aprendida ya lo permite
    [(numero, aviso)] = whatsapp.enviados  # pero la respuesta aún se propone (no es de confianza)
    assert numero == DUENO and "📩" in aviso


async def test_a_denied_permission_is_never_used(mundo):
    store, whatsapp, recepcionista, consultas = mundo
    await store.wa_guardar_contacto(DUENO, "Juan")
    await recepcionista.recibir(mensaje(PEDRO, "¿Cómo va mi orden?"))
    [pendiente] = await store.wa_pendientes()

    await decidir(recepcionista, id=pendiente.id, decision="negar")

    assert consultas == []


async def test_after_24_hours_the_user_is_alerted_with_the_approved_template(mundo):
    store, whatsapp, recepcionista, _ = mundo
    recepcionista._now = lambda: datetime.now(UTC) + timedelta(days=2)
    await store.wa_guardar_contacto(DUENO, "Juan")

    await recepcionista.recibir(mensaje(PEDRO, "Hola"))
    await recepcionista.recibir(mensaje(PEDRO, "¿Hola?"))

    assert whatsapp.enviados == []
    assert whatsapp.plantillas == [(DUENO, "aviso_azul")]  # una sola, no una por mensaje


async def test_rules_can_be_taught_listed_and_forgotten(mundo):
    store, _, recepcionista, _ = mundo
    await store.wa_guardar_contacto(PEDRO, "Pedro Gómez")
    herramientas = {h.name: h for h in recepcionista.herramientas_del_dueno()}

    await herramientas["whatsapp_regla"].handler(
        {"contacto": "pedro", "herramienta": "responder", "descripcion": "Es mi hermano"}
    )
    listado = json.loads(await herramientas["whatsapp_contactos"].handler({}))
    [regla] = listado[0]["reglas"]
    await herramientas["whatsapp_olvidar_regla"].handler({"id": regla["id"]})

    assert regla["regla"] == "Es mi hermano"
    assert await store.wa_reglas(PEDRO) == []
    with pytest.raises(ValueError, match="Herramienta desconocida"):
        await herramientas["whatsapp_regla"].handler(
            {"contacto": "pedro", "herramienta": "borrar_todo", "descripcion": "x"}
        )


async def test_contacts_have_their_own_history_apart_from_the_users(tmp_path):
    store = SqliteStore(tmp_path / "azul.db")
    pedro = store.memoria_de(PEDRO)

    await pedro.add_message(_mensaje("user", "Hola"))

    assert await store.message_count() == 0
    assert await pedro.message_count() == 1
    assert await store.memoria_de("otro").message_count() == 0


# --- Meta ---


def firmar(cuerpo: bytes, secreto="secreto") -> str:
    return "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()


AVISO = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "contacts": [{"wa_id": PEDRO, "profile": {"name": "Pedro"}}],
                        "messages": [
                            {
                                "from": PEDRO,
                                "id": "wamid.A",
                                "type": "text",
                                "text": {"body": "Hola"},
                            },
                            {"from": PEDRO, "id": "wamid.B", "type": "audio", "audio": {}},
                        ],
                    }
                }
            ]
        }
    ]
}


def test_messages_are_read_from_metas_notice():
    texto, audio = mensajes_de(AVISO)

    assert texto == MensajeEntrante("wamid.A", PEDRO, "Pedro", "text", "Hola")
    assert audio.tipo == "audio" and audio.texto == ""
    assert mensajes_de({"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}) == []


def test_the_receiver_only_accepts_notices_signed_by_meta():
    recibidos = []

    async def al_recibir(m):
        recibidos.append(m)

    cliente = TestClient(crear_receptor("secreto", "mi frase", al_recibir))
    cuerpo = json.dumps(AVISO).encode()

    falso = cliente.post(
        "/whatsapp", content=cuerpo, headers={"x-hub-signature-256": firmar(cuerpo, "otro")}
    )
    bueno = cliente.post(
        "/whatsapp", content=cuerpo, headers={"x-hub-signature-256": firmar(cuerpo)}
    )

    assert falso.status_code == 401
    assert bueno.status_code == 200
    assert [m.id for m in recibidos] == ["wamid.A", "wamid.B"]
    assert cliente.get("/").status_code == 404  # nada más de Azul está expuesto


def test_meta_can_verify_the_address_with_the_users_phrase():
    async def nada(m):
        pass

    cliente = TestClient(crear_receptor("secreto", "mi frase", nada))
    params = {"hub.mode": "subscribe", "hub.challenge": "123"}

    assert cliente.get("/whatsapp", params={**params, "hub.verify_token": "mi frase"}).text == "123"
    assert (
        cliente.get("/whatsapp", params={**params, "hub.verify_token": "otra"}).status_code == 403
    )


async def test_sending_posts_a_text_and_explains_the_24_hour_limit():
    pedidos = []

    def responder(request):
        pedidos.append(request)
        if len(pedidos) == 1:
            return httpx2.Response(200, json={"messages": [{"id": "x"}]})
        return httpx2.Response(400, json={"error": {"code": 131047}})

    meta = WhatsAppMeta("token", "123", transport=httpx2.MockTransport(responder))

    await meta.enviar(PEDRO, "Hola")
    with pytest.raises(WhatsAppError, match="24 horas"):
        await meta.enviar(PEDRO, "¿Sigues ahí?")

    cuerpo = json.loads(pedidos[0].content)
    assert pedidos[0].url.path == "/v23.0/123/messages"
    assert pedidos[0].headers["authorization"] == "Bearer token"
    assert cuerpo["to"] == PEDRO and cuerpo["text"]["body"] == "Hola"


def test_with_whatsapp_configured_azul_opens_a_separate_receiver(settings):
    from azul.main import create_app
    from tests.fakes import FakeBrain, FakeSpeechToText, FakeTextToSpeech

    configurado = settings.model_copy(
        update={
            "whatsapp_dueno": DUENO,
            "whatsapp_secreto_app": SecretStr("secreto"),
            "whatsapp_token_verificacion": SecretStr("mi frase"),
        }
    )
    sin_whatsapp = create_app(
        settings, brain=FakeBrain(), stt=FakeSpeechToText([]), tts=FakeTextToSpeech()
    )
    con_whatsapp = create_app(
        configurado,
        brain=FakeBrain(),
        stt=FakeSpeechToText([]),
        tts=FakeTextToSpeech(),
        whatsapp=WhatsAppFalso(),
    )

    assert sin_whatsapp.state.receptor_whatsapp is None
    receptor = TestClient(con_whatsapp.state.receptor_whatsapp)
    params = {"hub.mode": "subscribe", "hub.challenge": "ok", "hub.verify_token": "mi frase"}
    assert receptor.get("/whatsapp", params=params).text == "ok"


async def test_alerts_arrive_as_text_and_as_azuls_voice(tmp_path):
    store = SqliteStore(tmp_path / "azul.db")
    whatsapp = WhatsAppFalso()

    async def voz(texto):
        return f"mp3:{texto}".encode()

    recepcionista = Recepcionista(whatsapp, store, DUENO, voz=voz)
    await store.wa_guardar_contacto(DUENO, "Juan")

    await recepcionista.avisar("🔴 Correo urgente", "Te llegó un correo urgente")

    assert whatsapp.enviados == [(DUENO, "🔴 Correo urgente")]
    assert whatsapp.audios == [(DUENO, "mp3:Te llegó un correo urgente".encode())]
