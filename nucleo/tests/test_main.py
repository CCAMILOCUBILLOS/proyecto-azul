from fastapi.testclient import TestClient

from azul import __version__
from azul.main import create_app


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
