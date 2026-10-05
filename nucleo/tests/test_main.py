import json

from fastapi.testclient import TestClient

from azul import __version__
from azul.core.ports import Usage
from azul.main import create_app
from tests.fakes import FakeBrain


def events_of(response):
    return [json.loads(line) for line in response.text.splitlines() if line]


def test_salud(settings):
    client = TestClient(create_app(settings))

    response = client.get("/api/salud")

    assert response.status_code == 200
    assert response.json() == {"estado": "ok", "version": __version__}


def test_serves_web_app_when_built(settings):
    settings.app_dist_dir.mkdir(parents=True)
    (settings.app_dist_dir / "index.html").write_text("<h1>Azul</h1>", encoding="utf-8")
    client = TestClient(create_app(settings))

    assert "Azul" in client.get("/").text
    assert client.get("/api/salud").status_code == 200


def test_runs_without_web_app(settings):
    client = TestClient(create_app(settings))

    assert client.get("/").status_code == 404


def test_chat_streams_events_and_updates_history_and_spending(settings):
    brain = FakeBrain(["¡Hola!", " ¿Qué más?", Usage("anthropic", 0.012)])
    client = TestClient(create_app(settings, brain=brain))

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
    client = TestClient(create_app(settings, brain=FakeBrain(error="Sin conexión.")))

    response = client.post("/api/chat", json={"texto": "hola"})

    assert events_of(response) == [
        {"tipo": "error", "mensaje": "Sin conexión."},
        {"tipo": "fin"},
    ]


def test_chat_without_key_explains_what_to_do(settings):
    client = TestClient(create_app(settings))

    events = events_of(client.post("/api/chat", json={"texto": "hola"}))

    assert events[0]["tipo"] == "error"
    assert "ANTHROPIC_API_KEY" in events[0]["mensaje"]


def test_chat_rejects_empty_text(settings):
    client = TestClient(create_app(settings, brain=FakeBrain()))

    assert client.post("/api/chat", json={"texto": "   "}).status_code == 422
