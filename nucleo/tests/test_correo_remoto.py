import base64
import importlib.util
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from pydantic import SecretStr

from azul.adapters.correo_outlook import CorreoOutlook
from azul.adapters.correo_remoto import ejecutor_remoto
from azul.config import REPO_ROOT
from azul.core.ports import CorreoError

pytestmark = pytest.mark.anyio

CLAVE = "abcd-efgh-jkmn-pqrs"


def cargar_ayudante():
    ruta = REPO_ROOT / "ayudante-optometria" / "ayudante_outlook.py"
    spec = importlib.util.spec_from_file_location("ayudante_outlook", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


ayudante = cargar_ayudante()


class OutlookError(Exception):
    pass


def atender(cuerpo, clave=CLAVE, ejecutar=None, metodo="POST", ruta="/outlook"):
    return ayudante.atender(
        metodo,
        ruta,
        clave,
        json.dumps(cuerpo).encode() if isinstance(cuerpo, dict) else cuerpo,
        CLAVE,
        ejecutar or (lambda accion, entrada: {"accion": accion, "entrada": entrada}),
        {"buscar": "", "borrador": ""},
        OutlookError,
    )


# --- El ayudante (corre en Optometría) ---


def test_the_helper_needs_its_key():
    assert atender({"accion": "buscar"}, clave="otra")[0] == 401
    assert atender({"accion": "buscar"}, clave="")[0] == 401
    assert atender({}, metodo="GET", ruta="/salud", clave="") == (200, {"estado": "ok"})
    assert atender({"accion": "ping"}) == (200, {"ok": True})


def test_the_helper_only_runs_known_actions():
    assert atender({"accion": "enviar"})[0] == 400
    assert atender(b"no es json")[0] == 400
    assert atender({"accion": "buscar"}, ruta="/otra")[0] == 404


def test_attachments_are_rebuilt_as_local_files_with_safe_names():
    vistos = {}

    def ejecutar(accion, entrada):
        [ruta] = entrada["adjuntos"]
        vistos["nombre"] = Path(ruta).name
        vistos["contenido"] = Path(ruta).read_bytes()
        vistos["carpeta"] = Path(ruta).parent
        return {"id": "x"}

    datos = base64.b64encode(b"%PDF carta").decode()
    codigo, _ = atender(
        {
            "accion": "borrador",
            "entrada": {
                "asunto": "A",
                "adjuntos": [],
                "archivos": [{"nombre": "..\\..\\Windows\\carta.pdf", "datos": datos}],
            },
        },
        ejecutar=ejecutar,
    )

    assert codigo == 200
    assert vistos["nombre"] == "carta.pdf"  # sin rutas que se salgan de la carpeta
    assert vistos["contenido"] == b"%PDF carta"
    assert not vistos["carpeta"].exists()  # la carpeta temporal se borra al terminar


def test_outlook_errors_come_back_as_plain_messages():
    def falla(accion, entrada):
        raise OutlookError("Outlook no pudo hacerlo.")

    assert atender({"accion": "buscar"}, ejecutar=falla) == (
        422,
        {"error": "Outlook no pudo hacerlo."},
    )


# --- Azul en el portátil ---


def test_the_laptop_sends_the_action_with_the_key_and_the_file_contents(tmp_path):
    pedidos = []

    def responder(request):
        pedidos.append(request)
        return httpx2.Response(200, json={"id": "borrador-1"})

    adjunto = tmp_path / "informe.pdf"
    adjunto.write_bytes(b"PDF")
    ejecutar = ejecutor_remoto(
        "https://optometria.ts.net:8443/", CLAVE, transport=httpx2.MockTransport(responder)
    )

    resultado = ejecutar("borrador", {"asunto": "A", "adjuntos": [str(adjunto)]})

    assert resultado == {"id": "borrador-1"}
    [pedido] = pedidos
    assert str(pedido.url) == "https://optometria.ts.net:8443/outlook"
    assert pedido.headers["x-azul-clave"] == CLAVE
    cuerpo = json.loads(pedido.content)
    assert cuerpo["accion"] == "borrador"
    assert cuerpo["entrada"]["adjuntos"] == []
    assert cuerpo["entrada"]["archivos"] == [
        {"nombre": "informe.pdf", "datos": base64.b64encode(b"PDF").decode()}
    ]


def test_the_laptop_explains_what_went_wrong():
    def con(codigo, cuerpo):
        return ejecutor_remoto(
            "https://x",
            CLAVE,
            transport=httpx2.MockTransport(lambda r: httpx2.Response(codigo, json=cuerpo)),
        )

    def caido(request):
        raise httpx2.ConnectError("sin red")

    with pytest.raises(CorreoError, match="clave"):
        con(401, {})("buscar", {})
    with pytest.raises(CorreoError, match="Outlook no pudo"):
        con(422, {"error": "Outlook no pudo hacerlo."})("buscar", {})
    with pytest.raises(CorreoError, match="Optometría"):
        ejecutor_remoto("https://x", CLAVE, transport=httpx2.MockTransport(caido))("buscar", {})


async def test_end_to_end_through_a_real_helper_server(monkeypatch):
    llamadas = []

    def ejecutar(accion, entrada):
        llamadas.append(accion)
        return {"correos": [{"id": "1", "asunto": "Hola", "vista": "Texto   largo"}]}

    monkeypatch.setattr(ayudante, "PUERTO", 0)
    guiones = SimpleNamespace(ejecutar=ejecutar, ACCIONES={"buscar": ""}, OutlookError=OutlookError)
    servidor = ayudante.crear_servidor(CLAVE, guiones)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        puerto = servidor.server_address[1]
        correo = CorreoOutlook(ejecutor_remoto(f"http://127.0.0.1:{puerto}", CLAVE))

        [encontrado] = await correo.buscar("hola", "recibidos", 7)
    finally:
        servidor.shutdown()

    assert llamadas == ["buscar"]
    assert encontrado["asunto"] == "Hola" and encontrado["vista"] == "Texto largo"


def test_azul_uses_the_optometria_outlook_when_configured(settings):
    from azul.main import build_correo

    remoto = settings.model_copy(
        update={
            "correo_remoto_url": "https://optometria.ts.net:8443",
            "correo_remoto_clave": SecretStr(CLAVE),
        }
    )

    assert build_correo(settings) is None  # pruebas: sin Outlook local
    assert isinstance(build_correo(remoto), CorreoOutlook)


def test_env_values_are_replaced_or_added_without_touching_the_rest(tmp_path):
    from azul.cli import poner_en_env

    env = tmp_path / ".env"
    env.write_text("A=1\nAZUL_CORREO_REMOTO_URL=vieja\n", encoding="utf-8")

    poner_en_env(env, "AZUL_CORREO_REMOTO_URL", "https://nueva")
    poner_en_env(env, "AZUL_CORREO_REMOTO_CLAVE", CLAVE)

    assert env.read_text(encoding="utf-8").splitlines() == [
        "A=1",
        "AZUL_CORREO_REMOTO_URL=https://nueva",
        f"AZUL_CORREO_REMOTO_CLAVE={CLAVE}",
    ]
