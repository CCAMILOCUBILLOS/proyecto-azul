"""El PC de Optometría, a través de su ayudante (ADR 0040, 0041).

Azul vive en el portátil, pero el correo real está en el Outlook de Optometría y
allá también hay archivos que manejar. Allá corre un ayudante pequeño
(ayudante-optometria/ayudante_outlook.py) que ejecuta los mismos guiones que Azul:
/outlook para el correo y /archivos para archivos y Python. Tailscale lo publica
solo dentro de la red privada del usuario y además exige su propia clave.

Los archivos para adjuntar están en el portátil: viajan dentro del pedido.
"""

import base64
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2

from azul.core.ports import CorreoError

log = logging.getLogger(__name__)

# Más que el tiempo máximo de Outlook allá (120 s), para recibir su propio aviso.
SEGUNDOS_REMOTO = 150.0
CABECERA = "X-Azul-Clave"

Ejecutar = Callable[[str, dict[str, Any]], dict[str, Any]]

_SIN_AYUDANTE = (
    "No pude comunicarme con el ayudante del PC de Optometría. ¿Está encendido y con el "
    "ayudante abierto?"
)


def ejecutor_remoto(
    url: str,
    clave: str,
    transport: httpx2.BaseTransport | None = None,
    *,
    ruta: str = "/outlook",
    error: type[Exception] = CorreoError,
) -> Ejecutar:
    destino = url.rstrip("/") + ruta

    def ejecutar(accion: str, entrada: dict[str, Any]) -> dict[str, Any]:
        pedido = {"accion": accion, "entrada": _con_archivos(entrada)}
        try:
            with httpx2.Client(timeout=SEGUNDOS_REMOTO, transport=transport) as cliente:
                respuesta = cliente.post(destino, headers={CABECERA: clave}, json=pedido)
        except httpx2.HTTPError as fallo:
            log.warning("El ayudante no respondió: %s", type(fallo).__name__)
            raise error(_SIN_AYUDANTE) from fallo
        if respuesta.status_code == 401:
            raise error("La clave del ayudante de Optometría no coincide.")
        try:
            datos = respuesta.json()
        except ValueError as fallo:
            raise error(_SIN_AYUDANTE) from fallo
        if respuesta.status_code >= 400:
            raise error(str(datos.get("error") or "El ayudante de Optometría falló."))
        return dict(datos)

    return ejecutar


def _con_archivos(entrada: dict[str, Any]) -> dict[str, Any]:
    """Las rutas del portátil no existen allá: se manda el contenido de cada archivo."""
    if not entrada.get("adjuntos"):
        return entrada
    archivos = [
        {
            "nombre": Path(ruta).name,
            "datos": base64.b64encode(Path(ruta).read_bytes()).decode("ascii"),
        }
        for ruta in entrada["adjuntos"]
    ]
    return {**entrada, "adjuntos": [], "archivos": archivos}
