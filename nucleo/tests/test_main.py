import json

from fastapi.testclient import TestClient

from azul import __version__
from azul.core.ports import Transcript, Usage
from azul.main import create_app
from tests.fakes import FakeBrain, FakeSpeechToText, FakeTextToSpeech


def local_client(app):
    """Cliente que llega desde el propio portátil (sin pasar por Tailscale)."""
    return TestClient(app, client=("127.0.0.1", 50000))


def events_of(response):
    return [json.loads(line) for line in response.text.splitlines() if line]


def test_salud(settings):
    client = local_client(create_app(settings))

    response = client.get("/api/salud")

    assert response.status_code == 200
    assert response.json() == {"estado": "ok", "version": __version__}


def test_serves_web_app_when_built(settings):
    settings.app_dist_dir.mkdir(parents=True)
    (settings.app_dist_dir / "index.html").write_text("<h1>Azul</h1>", encoding="utf-8")
    client = local_client(create_app(settings))

    assert "Azul" in client.get("/").text
    assert client.get("/api/salud").status_code == 200


def test_web_app_pages_are_always_revalidated(settings):
    # Sin esto, el navegador mostraba la versión anterior de la app tras actualizarla.
    settings.app_dist_dir.mkdir(parents=True)
    (settings.app_dist_dir / "index.html").write_text("<h1>Azul</h1>", encoding="utf-8")
    (settings.app_dist_dir / "assets").mkdir()
    (settings.app_dist_dir / "assets" / "index-abc.js").write_text("1", encoding="utf-8")
    client = local_client(create_app(settings))

    assert client.get("/").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/assets/index-abc.js").headers


def test_runs_without_web_app(settings):
    client = local_client(create_app(settings))

    assert client.get("/").status_code == 404


def test_chat_streams_events_and_updates_history_and_spending(settings):
    brain = FakeBrain(["¡Hola!", " ¿Qué más?", Usage("anthropic", 0.012)])
    client = local_client(create_app(settings, brain=brain))

    response = client.post("/api/chat", json={"texto": "  hola  "})

    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert events_of(response) == [
        {"tipo": "texto", "texto": "¡Hola!"},
        {"tipo": "texto", "texto": " ¿Qué más?"},
        {"tipo": "fin"},
    ]
    assert [(m["rol"], m["texto"]) for m in client.get("/api/historial").json()] == [
        ("user", "hola"),
        ("assistant", "¡Hola! ¿Qué más?"),
    ]
    assert client.get("/api/gasto").json() == {"gastado_mes": 0.012, "limite": 50.0, "aviso": 40.0}


def test_chat_reports_brain_errors(settings):
    client = local_client(create_app(settings, brain=FakeBrain(error="Sin conexión.")))

    response = client.post("/api/chat", json={"texto": "hola"})

    assert events_of(response) == [
        {"tipo": "error", "mensaje": "Sin conexión."},
        {"tipo": "fin"},
    ]


def test_chat_without_key_explains_what_to_do(settings):
    client = local_client(create_app(settings))

    events = events_of(client.post("/api/chat", json={"texto": "hola"}))

    assert events[0]["tipo"] == "error"
    assert "ANTHROPIC_API_KEY" in events[0]["mensaje"]


def test_chat_rejects_empty_text(settings):
    client = local_client(create_app(settings, brain=FakeBrain()))

    assert client.post("/api/chat", json={"texto": "   "}).status_code == 422


def receive_until_end(socket):
    """Recibe eventos de voz hasta "fin"; el audio llega como binario."""
    received = []
    while True:
        message = socket.receive()
        if message.get("bytes") is not None:
            received.append(message["bytes"])
            continue
        event = json.loads(message["text"])
        received.append(event)
        if event["tipo"] == "fin":
            return received


def test_voice_turn_over_websocket(settings):
    stt = FakeSpeechToText([Transcript("¿Cómo estás?", True)])
    tts = FakeTextToSpeech()
    app = create_app(settings, brain=FakeBrain(["¡Muy bien! ", "¿Y tú?"]), stt=stt, tts=tts)

    with local_client(app).websocket_connect("/api/voz") as socket:
        socket.send_json({"tipo": "hablar_inicio"})
        socket.send_bytes(b"pcm-1")
        socket.send_bytes(b"pcm-2")
        socket.send_json({"tipo": "hablar_fin"})
        received = receive_until_end(socket)

    assert stt.received == [b"pcm-1", b"pcm-2"]
    assert {"tipo": "escuchado", "texto": "¿Cómo estás?", "final": True} in received
    texts = [r["texto"] for r in received if isinstance(r, dict) and r["tipo"] == "texto"]
    assert "".join(texts) == "¡Muy bien! ¿Y tú?"
    assert [r for r in received if isinstance(r, bytes)] == [
        b"<\xc2\xa1Muy bien!>",
        b"<\xc2\xbfY t\xc3\xba?>",
    ]


def test_voice_stop_command_over_websocket(settings):
    stt = FakeSpeechToText([Transcript("Para.", True)])
    brain = FakeBrain(["no"])
    app = create_app(settings, brain=brain, stt=stt, tts=FakeTextToSpeech())

    with local_client(app).websocket_connect("/api/voz") as socket:
        socket.send_json({"tipo": "hablar_inicio"})
        socket.send_json({"tipo": "hablar_fin"})
        received = receive_until_end(socket)

    assert {"tipo": "parado"} in received
    assert brain.requests == []


def test_voice_without_deepgram_key_explains_what_to_do(settings):
    app = create_app(settings, brain=FakeBrain())

    with local_client(app).websocket_connect("/api/voz") as socket:
        socket.send_json({"tipo": "hablar_inicio"})
        socket.send_json({"tipo": "hablar_fin"})
        received = receive_until_end(socket)

    assert received[0] == {"tipo": "turno"}
    assert received[1]["tipo"] == "error"
    assert "DEEPGRAM_API_KEY" in received[1]["mensaje"]


def test_precalentar_endpoint(settings):
    brain = FakeBrain()
    client = local_client(create_app(settings, brain=brain))

    assert client.post("/api/precalentar").status_code == 204
    assert len(brain.prewarms) == 1


def test_wake_mode_over_websocket(settings):
    stt = FakeSpeechToText([Transcript("Oye Azul, ¿cómo estás?", True)])
    brain = FakeBrain(["¡Muy bien!"])
    app = create_app(settings, brain=brain, stt=stt, tts=FakeTextToSpeech())

    with local_client(app).websocket_connect("/api/voz") as socket:
        socket.send_json({"tipo": "activacion_inicio"})
        socket.send_bytes(b"pcm")
        socket.send_json({"tipo": "activacion_fin"})
        received = receive_until_end(socket)

    assert {"tipo": "escuchado", "texto": "¿cómo estás?", "final": True} in received
    assert brain.requests[0].messages[-1].text == "¿cómo estás?"


def test_wake_mode_ignores_other_speech_over_websocket(settings):
    stt = FakeSpeechToText([Transcript("pásame la sal", True)])
    app = create_app(settings, brain=FakeBrain(["no"]), stt=stt, tts=FakeTextToSpeech())

    with local_client(app).websocket_connect("/api/voz") as socket:
        socket.send_json({"tipo": "activacion_inicio"})
        socket.send_json({"tipo": "activacion_fin"})
        received = receive_until_end(socket)

    assert received == [
        {"tipo": "turno"},
        {"tipo": "ignorado", "con_palabras": True},
        {"tipo": "fin"},
    ]


def test_preguntar_returns_the_whole_answer_as_text(settings):
    brain = FakeBrain(["¡Hola, ", "Camilo!", " <recordar>Usa Siri.</recordar>"])
    client = local_client(create_app(settings, brain=brain))

    response = client.post("/api/preguntar", json={"texto": "hola"})

    assert response.json() == {"respuesta": "¡Hola, Camilo!"}


def test_preguntar_explains_errors(settings):
    client = local_client(create_app(settings, brain=FakeBrain(error="Sin conexión.")))

    assert client.post("/api/preguntar", json={"texto": "hola"}).json() == {
        "respuesta": "Sin conexión."
    }


def test_conocimiento_counts_memories_skills_and_tools(settings):
    client = local_client(create_app(settings, brain=FakeBrain()))

    datos = client.get("/api/conocimiento").json()

    assert datos["recuerdos"] == 0
    assert "redaccion" in datos["habilidades"]
    assert {"busqueda_web", "clima", "crear_word"} <= set(datos["herramientas"])
    assert datos["mensajes"] == 0
    assert datos["etiquetas"]["herramientas"]["clima"] == "Clima"
    assert datos["etiquetas"]["habilidades"]["redaccion"].startswith("Redactar o corregir")
    assert datos["etiquetas"]["recuerdos"] == []


class FakeVerificador:
    def __init__(self, es_el_usuario=True, inscrito=True):
        self.respuesta = es_el_usuario
        self.inscrito = inscrito
        self.muestras = 0
        self.verificado = []

    async def agregar_muestra(self, pcm):
        if len(pcm) < 10:
            raise ValueError("No oí suficiente voz.")
        self.muestras += 1
        return self.muestras

    async def terminar_inscripcion(self):
        self.inscrito = True

    async def borrar(self):
        self.inscrito = False

    async def es_el_usuario(self, pcm):
        return await self.veredicto(pcm) == "si"

    async def veredicto(self, pcm):
        self.verificado.append(len(pcm))
        if isinstance(self.respuesta, list):
            return self.respuesta.pop(0)
        return "si" if self.respuesta else "no"


def interrupcion(socket, segundos=2.4):
    socket.send_json({"tipo": "interrupcion_inicio"})
    for _ in range(int(segundos * 10)):
        socket.send_bytes(b"\0" * 3200)


def test_user_voice_interrupts_and_opens_a_new_turn(settings):
    verificador = FakeVerificador(es_el_usuario=True)
    stt = FakeSpeechToText([Transcript("No, espera.", True)])
    brain = FakeBrain(["Vale."])
    app = create_app(
        settings, brain=brain, stt=stt, tts=FakeTextToSpeech(), verificador=verificador
    )

    with local_client(app).websocket_connect("/api/voz") as socket:
        interrupcion(socket)
        assert socket.receive_json() == {"tipo": "interrumpido"}
        socket.send_json({"tipo": "hablar_fin"})
        recibido = receive_until_end(socket)

    assert recibido[0] == {"tipo": "turno"}
    assert brain.requests[0].messages[-1].text == "No, espera."
    assert verificador.verificado[0] >= 16_000 * 2 * 2.2


def test_a_doubtful_voice_is_checked_again_with_more_audio(settings):
    verificador = FakeVerificador(es_el_usuario=["dudoso", "si"])
    stt = FakeSpeechToText([Transcript("Espera.", True)])
    app = create_app(
        settings, brain=FakeBrain(["Ok."]), stt=stt, tts=FakeTextToSpeech(), verificador=verificador
    )

    with local_client(app).websocket_connect("/api/voz") as socket:
        interrupcion(socket, segundos=3.7)
        assert socket.receive_json() == {"tipo": "interrumpido"}

    assert verificador.verificado[1] >= 16_000 * 2 * 3.5


def test_other_voices_do_not_interrupt(settings):
    app = create_app(
        settings,
        brain=FakeBrain(),
        stt=FakeSpeechToText([]),
        tts=FakeTextToSpeech(),
        verificador=FakeVerificador(es_el_usuario=False),
    )

    with local_client(app).websocket_connect("/api/voz") as socket:
        interrupcion(socket)
        assert socket.receive_json() == {"tipo": "no_eres_tu"}


def test_interrupting_needs_an_enrolled_voice(settings):
    app = create_app(settings, brain=FakeBrain(), verificador=FakeVerificador(inscrito=False))

    with local_client(app).websocket_connect("/api/voz") as socket:
        socket.send_json({"tipo": "interrupcion_inicio"})
        assert socket.receive_json() == {
            "tipo": "interrupcion_no_disponible",
            "motivo": "sin_huella",
        }


def test_voice_enrollment_endpoints(settings):
    verificador = FakeVerificador(inscrito=False)
    client = local_client(create_app(settings, brain=FakeBrain(), verificador=verificador))

    assert client.get("/api/huella").json() == {
        "disponible": True,
        "inscrita": False,
        "muestras": 0,
    }
    assert client.post("/api/huella/muestra", content=b"\0" * 32_000).json() == {"muestras": 1}
    assert client.post("/api/huella/muestra", content=b"\0").status_code == 422
    assert client.post("/api/huella/listo").status_code == 204
    assert client.get("/api/huella").json()["inscrita"] is True
    assert client.delete("/api/huella").status_code == 204
    assert client.get("/api/huella").json()["inscrita"] is False
