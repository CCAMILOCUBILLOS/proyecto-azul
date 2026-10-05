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
    assert {"tipo": "texto", "texto": "¡Muy bien! "} in received
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
