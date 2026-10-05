"""Control de acceso (ADR 0003, 0012).

- Desde el propio portátil (navegador local) no se pide clave.
- Desde otros dispositivos, que llegan por Tailscale, se exige la clave de la
  app: el usuario la escribe una vez y queda guardada en una cookie segura.

Tailscale entrega las peticiones desde 127.0.0.1, así que una petición es
"local" solo si además no trae las cabeceras que agrega el proxy.
"""

import hashlib
import hmac
import logging
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

log = logging.getLogger(__name__)

COOKIE_NAME = "azul_acceso"
COOKIE_MAX_AGE = 365 * 24 * 3600
KEY_HEADER = b"x-azul-clave"

# Rutas que funcionan sin clave: lo mínimo para mostrar la pantalla de entrada.
OPEN_API_PATHS = frozenset({"/api/salud", "/api/sesion", "/api/entrar"})

_LOOPBACK = frozenset({"127.0.0.1", "::1"})
_PROXY_HEADERS = (b"x-forwarded-for", b"tailscale-user-login")

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def is_local(scope: Scope) -> bool:
    client = scope.get("client")
    if not client or client[0] not in _LOOPBACK:
        return False
    headers = dict(scope.get("headers") or [])
    return not any(name in headers for name in _PROXY_HEADERS)


def session_token(access_key: str) -> str:
    """Valor de la cookie: deriva de la clave, sin guardarla tal cual en el navegador."""
    return hmac.new(access_key.encode(), b"azul-sesion-v1", hashlib.sha256).hexdigest()


def is_authorized(scope: Scope, access_key: str | None) -> bool:
    if is_local(scope):
        return True
    if not access_key:
        return False
    cookie = _cookie(scope, COOKIE_NAME)
    if cookie is not None and hmac.compare_digest(cookie, session_token(access_key)):
        return True
    # Los Atajos del iPhone (Siri) no manejan cookies: envían la clave en una cabecera.
    header = dict(scope.get("headers") or []).get(KEY_HEADER)
    return header is not None and key_matches(header.decode("latin-1"), access_key)


def key_matches(candidate: str, access_key: str | None) -> bool:
    return bool(access_key) and hmac.compare_digest(candidate.encode(), access_key.encode())


class AccessMiddleware:
    """Protege /api (HTTP y WebSocket) para quien no esté en el propio portátil."""

    def __init__(self, app: ASGIApp, access_key: str | None) -> None:
        self._app = app
        self._access_key = access_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        protected = (
            scope["type"] in ("http", "websocket")
            and path.startswith("/api/")
            and path not in OPEN_API_PATHS
        )
        if not protected or is_authorized(scope, self._access_key):
            await self._app(scope, receive, send)
            return
        _log_rejection(scope, self._access_key)
        if scope["type"] == "websocket":
            # Cerrar antes de aceptar equivale a rechazar la conexión (HTTP 403).
            await send({"type": "websocket.close", "code": 4401})
            return
        body = b'{"detalle":"Falta la clave de acceso de Azul."}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _log_rejection(scope: Scope, access_key: str | None) -> None:
    """Anota por qué se rechazó una petición, sin escribir nunca la clave."""
    header = dict(scope.get("headers") or []).get(KEY_HEADER)
    if access_key is None:
        reason = "no hay clave configurada"
    elif header is None:
        reason = "sin cookie de sesión ni cabecera X-Azul-Clave"
    else:
        value = header.decode("latin-1")
        reason = (
            f"la cabecera X-Azul-Clave no coincide ({len(value)} caracteres; se esperan "
            f"{len(access_key)}; coincide sin mayúsculas ni espacios: "
            f"{value.strip().lower() == access_key.lower()})"
        )
    log.warning("Acceso rechazado a %s: %s", scope.get("path"), reason)


def _cookie(scope: Scope, name: str) -> str | None:
    for header, value in scope.get("headers") or []:
        if header != b"cookie":
            continue
        for part in value.decode("latin-1").split(";"):
            key, _, cookie_value = part.strip().partition("=")
            if key == name:
                return cookie_value
    return None
