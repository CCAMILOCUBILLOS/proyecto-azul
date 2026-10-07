"""El tablero de Red Nacional por HTTP (ADR 0031).

El tablero (tablero.py) escucha solo en su propio PC; Tailscale lo publica
dentro de la red privada del usuario y Azul le habla en esa dirección
(AZUL_RED_NACIONAL_URL). Se usan las mismas rutas que usan sus botones.
"""

import logging
from typing import Any

import httpx2

from azul.core.ports import RedNacionalError

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30.0

# Sección -> (ruta, parámetros que acepta).
_CONSULTAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "resumen": ("/api/resumen", ()),
    "seguimiento": ("/api/seguimiento", ()),
    "progreso": ("/api/log", ()),
    "ventas": ("/api/ventas", ()),
    "ventas_red": ("/api/ventas/red", ()),
    "control": ("/api/control", ()),
    "directorio": ("/api/directorio", ()),
    "clientes": ("/api/clientes", ()),
    "cliente_perfil": ("/api/clientes/perfil", ("clave",)),
    "cliente_bateria": ("/api/clientes/bateria", ("nombre",)),
    "cliente_cargo": ("/api/clientes/cargo", ("clave", "cargo")),
    "cliente_acuerdo": ("/api/clientes/acuerdo", ("clave",)),
}

# Procesos que el tablero lanza con su botón genérico (/api/lanzar).
_LANZABLES = {
    "simulacion",
    "verificar",
    "cargue",
    "correos",
    "agendar_simulacion",
    "agendar",
    "base",
    "ventas",
    "ventas_acuerdos",
    "control_probar",
    "control_sync",
    "control_conectar",
}

# Lo que el tablero espera en cada proceso: lo demás no se envía.
_CAMPOS = {
    "cargue": ("maximo", "confirmacion"),
    "correos": ("desde", "hasta"),
    "agendar_simulacion": ("desde", "hasta"),
    "agendar": ("desde", "hasta"),
    "base": ("desde", "hasta"),
    "ventas": ("desde", "hasta", "biofile", "drive", "informe"),
    "sincronizar_seguimiento": ("desde", "hasta"),
    "marcar_seguimiento": ("id", "estado"),
}

_OTRAS_RUTAS = {
    "detener": "/api/detener",
    "sincronizar_seguimiento": "/api/seguimiento/sync",
    "marcar_seguimiento": "/api/seguimiento/marcar",
    "reporte": "/api/reporte",
}

NO_RESPONDE = (
    "No encuentro el tablero de Red Nacional. Revisa que el PC de Optometría esté prendido, "
    "con Tablero.bat abierto y Tailscale conectado."
)


class TableroRedNacional:
    def __init__(self, base_url: str, client: httpx2.AsyncClient | None = None) -> None:
        self._client = client or httpx2.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=TIMEOUT_SECONDS
        )

    async def consultar(self, seccion: str, parametros: dict[str, str]) -> Any:
        if seccion not in _CONSULTAS:
            raise RedNacionalError(f"No conozco la sección «{seccion}».")
        ruta, aceptados = _CONSULTAS[seccion]
        params = {clave: parametros[clave] for clave in aceptados if clave in parametros}
        if seccion == "progreso":
            params["desde"] = "0"
        return await self._pedir("GET", ruta, params=params)

    async def ejecutar(self, operacion: str, datos: dict[str, Any]) -> Any:
        cuerpo = {clave: datos[clave] for clave in _CAMPOS.get(operacion, ()) if clave in datos}
        if operacion in _LANZABLES:
            return await self._pedir("POST", "/api/lanzar", json={"accion": operacion, **cuerpo})
        if operacion in _OTRAS_RUTAS:
            return await self._pedir("POST", _OTRAS_RUTAS[operacion], json=cuerpo)
        raise RedNacionalError(f"No conozco el proceso «{operacion}».")

    async def _pedir(self, metodo: str, ruta: str, **opciones: Any) -> Any:
        try:
            respuesta = await self._client.request(metodo, ruta, **opciones)
        except httpx2.HTTPError as error:
            log.warning("Tablero de Red Nacional sin respuesta: %s", type(error).__name__)
            raise RedNacionalError(NO_RESPONDE) from error
        try:
            datos = respuesta.json()
        except ValueError:
            datos = None
        # El tablero contesta {"ok": false, "motivo": ...} cuando algo no se puede (409/400…):
        # eso se le pasa tal cual a Azul para que lo explique.
        if datos is None:
            if respuesta.status_code == 404:
                raise RedNacionalError("El tablero no tiene esa función (¿versión distinta?).")
            raise RedNacionalError(f"El tablero respondió con un error ({respuesta.status_code}).")
        return datos
