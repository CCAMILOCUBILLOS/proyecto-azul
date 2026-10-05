import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from azul.access import COOKIE_NAME, session_token
from azul.config import Settings
from azul.main import create_app
from tests.fakes import FakeBrain

KEY = "tres palabras 7"
# Así llegan las peticiones a través de Tailscale: desde 127.0.0.1, con cabeceras del proxy.
VIA_TAILSCALE = {"X-Forwarded-For": "100.64.0.5", "Tailscale-User-Login": "camilo@gmail.com"}


@pytest.fixture
def settings_with_key(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "datos",
        app_dist_dir=tmp_path / "dist",
        access_key=KEY,
    )


def remote_client(settings, **kwargs):
    app = create_app(settings, brain=FakeBrain(["ok"]))
    return TestClient(app, client=("127.0.0.1", 50000), headers=VIA_TAILSCALE, **kwargs)


def test_local_browser_needs_no_key(settings_with_key):
    client = TestClient(create_app(settings_with_key), client=("127.0.0.1", 50000))

    assert client.get("/api/gasto").status_code == 200
    assert client.get("/api/sesion").json() == {
        "local": True,
        "autorizado": True,
        "clave_configurada": True,
    }


def test_phone_without_key_is_rejected(settings_with_key):
    client = remote_client(settings_with_key)

    response = client.get("/api/historial")

    assert response.status_code == 401
    assert client.get("/api/sesion").json()["autorizado"] is False
    assert client.get("/api/salud").status_code == 200  # para mostrar la pantalla de entrada


def test_unknown_network_client_is_rejected(settings_with_key):
    client = TestClient(create_app(settings_with_key), client=("192.168.1.20", 50000))

    assert client.get("/api/gasto").status_code == 401


def test_wrong_key_is_refused(settings_with_key):
    client = remote_client(settings_with_key)

    response = client.post("/api/entrar", json={"clave": "otra"})

    assert response.status_code == 401
    assert COOKIE_NAME not in response.cookies


def test_right_key_opens_a_lasting_session(settings_with_key):
    client = remote_client(settings_with_key, base_url="https://azul.ts.net")

    response = client.post("/api/entrar", json={"clave": KEY})

    assert response.status_code == 204
    cookie_header = response.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "Secure" in cookie_header
    assert "samesite=strict" in cookie_header.lower()
    assert KEY not in cookie_header  # la cookie no guarda la clave tal cual
    assert client.get("/api/historial").status_code == 200


def test_voice_socket_requires_key_from_phone(settings_with_key):
    client = remote_client(settings_with_key)

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/voz"):
        pass

    client.cookies.set(COOKIE_NAME, session_token(KEY))
    with client.websocket_connect("/api/voz") as socket:
        socket.send_json({"tipo": "parar"})


def test_phone_access_without_configured_key_explains_what_to_do(settings):
    client = remote_client(settings)

    response = client.post("/api/entrar", json={"clave": "lo que sea"})

    assert response.status_code == 503
    assert "AZUL_ACCESS_KEY" in response.json()["detail"]
    assert client.get("/api/historial").status_code == 401
