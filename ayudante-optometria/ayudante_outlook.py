"""Ayudante de Azul para el PC de Optometría (ADR 0040, 0041).

Azul vive en el portátil; el correo real está en el Outlook de este PC. Este
programa pequeño atiende los pedidos de Azul con los mismos archivos que usa Azul:
- /outlook: buscar, leer, dejar borradores, responder y poner categorías
  (nucleo/src/azul/adapters/outlook_powershell.py). Nunca envía correos.
- /archivos: listar, buscar, leer, editar (con copia de seguridad en .\\respaldos),
  organizar y correr Python en .\\trabajo (nucleo/src/azul/adapters/archivos_basicos.py).

- Solo escucha en este equipo (127.0.0.1). Tailscale lo publica dentro de la red
  privada del usuario: tailscale serve --bg --https=8443 http://127.0.0.1:8767
- Cada pedido debe traer la clave del ayudante (cabecera X-Azul-Clave). La primera
  vez se crea sola y se guarda en el archivo .clave, junto a este programa.
- Solo usa la biblioteca estándar de Python (3.8 o más nueva).
- El registro (ayudante.log) no guarda el contenido de ningún correo.
"""

from __future__ import annotations

import base64
import hmac
import importlib.util
import json
import logging
import os
import secrets
import tempfile
import threading
from collections import defaultdict
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
ADAPTADORES = AQUI.parent / "nucleo" / "src" / "azul" / "adapters"
ARCHIVO_CLAVE = AQUI / ".clave"
PUERTO = int(os.environ.get("AZUL_AYUDANTE_PUERTO", "8767"))
MAX_BYTES = 32 * 1024 * 1024  # 20 MB de adjuntos, más lo que agranda base64
CABECERA = "X-Azul-Clave"
LETRAS_DE_CLAVE = "abcdefghjkmnpqrstuvwxyz23456789"

log = logging.getLogger("ayudante")


def cargar(nombre: str) -> Any:
    """Un archivo de Azul sin importar el resto de Azul (que aquí no está instalado)."""
    ruta = ADAPTADORES / f"{nombre}.py"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    if spec is None or spec.loader is None or not ruta.exists():
        raise SystemExit(f"No encuentro {ruta}. ¿Está completa la carpeta de Azul?")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def servicios_de_este_pc() -> dict[str, tuple[Any, Any, type]]:
    """Ruta -> (ejecutar, acciones, error) de cada servicio del ayudante."""
    guiones = cargar("outlook_powershell")
    archivos = cargar("archivos_basicos")
    config = {
        "respaldos": str(AQUI / "respaldos"),
        "trabajo": str(AQUI / "trabajo"),
        "raices": archivos.raices_por_defecto(),
    }
    return {
        "/outlook": (guiones.ejecutar, guiones.ACCIONES, guiones.OutlookError),
        "/archivos": (
            lambda accion, entrada: archivos.ejecutar(accion, entrada, config),
            archivos.ACCIONES,
            archivos.ArchivoError,
        ),
    }


def obtener_clave() -> str:
    clave = os.environ.get("AZUL_AYUDANTE_CLAVE", "").strip()
    if clave:
        return clave
    if ARCHIVO_CLAVE.exists():
        return ARCHIVO_CLAVE.read_text(encoding="utf-8").strip()
    grupos = ["".join(secrets.choice(LETRAS_DE_CLAVE) for _ in range(4)) for _ in range(4)]
    clave = "-".join(grupos)
    ARCHIVO_CLAVE.write_text(clave, encoding="utf-8")
    print("Primera vez: se creó la clave del ayudante. Escríbela en el portátil, en")
    print("'Conectar correo de Optometria.cmd':")
    print()
    print(f"    {clave}")
    print()
    return clave


def atender(
    metodo: str,
    ruta: str,
    clave_recibida: str,
    cuerpo: bytes,
    clave: str,
    servicios: dict[str, tuple[Callable[[str, dict[str, Any]], dict[str, Any]], Any, type]],
) -> tuple[int, dict[str, Any]]:
    """Un pedido de Azul -> (código HTTP, respuesta). Separado del servidor para probarlo."""
    if metodo == "GET" and ruta == "/salud":
        return 200, {"estado": "ok"}
    if metodo != "POST" or ruta not in servicios:
        return 404, {"error": "No existe."}
    ejecutar, acciones, error_del_servicio = servicios[ruta]
    if not clave_recibida or not hmac.compare_digest(clave_recibida, clave):
        return 401, {"error": "Clave incorrecta."}
    try:
        pedido = json.loads(cuerpo)
        accion = str(pedido["accion"])
        entrada = dict(pedido.get("entrada") or {})
    except (ValueError, KeyError, TypeError):
        return 400, {"error": "Pedido mal formado."}
    if accion == "ping":
        return 200, {"ok": True}
    if accion not in acciones:
        return 400, {"error": "Acción desconocida."}
    with tempfile.TemporaryDirectory(prefix="azul-adjuntos-") as carpeta:
        try:
            entrada = _guardar_archivos(entrada, Path(carpeta))
        except (ValueError, KeyError, TypeError):
            return 400, {"error": "Adjuntos mal formados."}
        try:
            # Un pedido a la vez por servicio: un programa largo no frena al correo.
            with _CANDADOS[ruta]:
                return 200, ejecutar(accion, entrada)
        except error_del_servicio as error:
            return 422, {"error": str(error)}
        except Exception:
            log.exception("Fallo inesperado atendiendo '%s %s'", ruta, accion)
            return 500, {"error": "El ayudante de Optometría falló; quedó en su registro."}


_CANDADOS: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def _guardar_archivos(entrada: dict[str, Any], carpeta: Path) -> dict[str, Any]:
    archivos = entrada.pop("archivos", None) or []
    rutas = []
    for archivo in archivos:
        # Solo el nombre: nada de rutas que se salgan de la carpeta temporal.
        nombre = Path(str(archivo["nombre"])).name or "adjunto"
        destino = carpeta / nombre
        destino.write_bytes(base64.b64decode(archivo["datos"], validate=True))
        rutas.append(str(destino))
    if rutas:
        entrada["adjuntos"] = rutas
    return entrada


def crear_servidor(clave: str, servicios: dict[str, Any]) -> ThreadingHTTPServer:
    class Manejador(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._responder("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._responder("POST")

        def _responder(self, metodo: str) -> None:
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > MAX_BYTES:
                codigo, datos = 413, {"error": "El pedido es demasiado grande."}
            else:
                cuerpo = self.rfile.read(largo) if largo else b""
                codigo, datos = atender(
                    metodo,
                    self.path,
                    self.headers.get(CABECERA, ""),
                    cuerpo,
                    clave,
                    servicios,
                )
            salida = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(salida)))
            self.end_headers()
            self.wfile.write(salida)

        def log_message(self, formato: str, *args: Any) -> None:
            # Solo método, ruta y código: nunca el contenido.
            log.info("%s %s", self.address_string(), formato % args)

    return ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)


def main() -> None:
    archivo = logging.FileHandler(str(AQUI / "ayudante.log"), encoding="utf-8")
    archivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[archivo])
    servicios = servicios_de_este_pc()
    clave = obtener_clave()
    servidor = crear_servidor(clave, servicios)
    print(f"Ayudante de Azul encendido en http://127.0.0.1:{PUERTO} (correo y archivos)")
    print("Déjalo abierto. Para apagarlo, cierra esta ventana.", flush=True)
    log.info("Ayudante encendido")
    servidor.serve_forever()


if __name__ == "__main__":
    main()
