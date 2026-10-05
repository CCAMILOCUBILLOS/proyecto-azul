"""Punto de entrada: crea la aplicación web y arranca el servidor."""

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from azul import __version__
from azul.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Azul", version=__version__)

    @app.get("/api/salud")
    async def salud() -> dict[str, str]:
        return {"estado": "ok", "version": __version__}

    # La app web compilada se sirve desde el mismo núcleo: un solo programa.
    # Se monta al final para que no tape las rutas /api.
    if settings.app_dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.app_dist_dir, html=True), name="app")

    return app


def run() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
