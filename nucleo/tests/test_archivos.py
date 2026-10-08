import json
from pathlib import Path

import pytest

from azul.adapters import archivos_basicos as ab
from azul.adapters.archivos_equipo import archivos_locales
from azul.core.herramientas_archivos import (
    SOLO_DEL_USUARIO,
    Confirmaciones,
    herramientas_archivos,
)
from azul.core.ports import ToolSpec

pytestmark = pytest.mark.anyio


@pytest.fixture
def carpeta(tmp_path):
    (tmp_path / "trabajo").mkdir()
    return tmp_path


def herramientas(carpeta, confirmaciones=None):
    equipos = {"portatil": archivos_locales(carpeta / "respaldos", carpeta / "trabajo")}
    lista = herramientas_archivos(equipos, confirmaciones or Confirmaciones(), lambda _: None)
    return {h.name: h for h in lista}


# --- Editar, con copia de seguridad y deshacer ---


def test_editing_backs_up_first_and_can_be_undone(carpeta):
    codigo = carpeta / "red_nacional.py"
    codigo.write_text('EXCLUIR = ["NO SE PRESENTO"]\n', encoding="utf-8")
    respaldos = str(carpeta / "respaldos")

    hecho = ab.editar(
        str(codigo),
        '["NO SE PRESENTO"]',
        '["NO SE PRESENTO", "PENDIENTES CAMILO"]',
        False,
        respaldos,
    )

    assert (
        codigo.read_text(encoding="utf-8") == 'EXCLUIR = ["NO SE PRESENTO", "PENDIENTES CAMILO"]\n'
    )
    assert Path(hecho["respaldo"]).read_text(encoding="utf-8") == 'EXCLUIR = ["NO SE PRESENTO"]\n'

    ab.restaurar(str(codigo), respaldos)

    assert codigo.read_text(encoding="utf-8") == 'EXCLUIR = ["NO SE PRESENTO"]\n'


def test_an_edit_must_match_exactly_once(carpeta):
    archivo = carpeta / "a.txt"
    archivo.write_text("hola hola", encoding="utf-8")
    respaldos = str(carpeta / "respaldos")

    with pytest.raises(ab.ArchivoError, match="No encontré"):
        ab.editar(str(archivo), "adiós", "x", False, respaldos)
    with pytest.raises(ab.ArchivoError, match="2 veces"):
        ab.editar(str(archivo), "hola", "x", False, respaldos)
    assert ab.editar(str(archivo), "hola", "chao", True, respaldos)["cambios"] == 2


def test_windows_line_endings_and_encoding_are_kept(carpeta):
    archivo = carpeta / "viejo.bat"
    archivo.write_bytes("echo canción\r\npause\r\n".encode("cp1252"))

    ab.editar(str(archivo), "echo canción\npause", "echo listo\npause", False, str(carpeta / "r"))

    assert archivo.read_bytes() == b"echo listo\r\npause\r\n"


def test_system_folders_and_secret_files_are_off_limits(carpeta):
    (carpeta / ".env").write_text("CLAVE=1", encoding="utf-8")

    with pytest.raises(ab.ArchivoError, match="sistema"):
        ab.validar(r"C:\Windows\System32\drivers\etc\hosts")
    with pytest.raises(ab.ArchivoError, match="claves"):
        ab.leer(str(carpeta / ".env"))
    with pytest.raises(ab.ArchivoError, match="ruta completa"):
        ab.validar("archivo.txt")


def test_copy_and_move_never_overwrite(carpeta):
    (carpeta / "a.txt").write_text("A", encoding="utf-8")
    (carpeta / "b.txt").write_text("B", encoding="utf-8")

    with pytest.raises(ab.ArchivoError, match="no lo sobrescribo"):
        ab.copiar(str(carpeta / "a.txt"), str(carpeta / "b.txt"))
    ab.mover(str(carpeta / "a.txt"), str(carpeta / "nueva" / "a.txt"))

    assert (carpeta / "nueva" / "a.txt").read_text(encoding="utf-8") == "A"
    assert (carpeta / "b.txt").read_text(encoding="utf-8") == "B"


def test_writing_over_a_file_keeps_a_backup(carpeta):
    archivo = carpeta / "notas.md"
    archivo.write_text("antes", encoding="utf-8")

    hecho = ab.escribir(str(archivo), "después", str(carpeta / "respaldos"))

    assert archivo.read_text(encoding="utf-8") == "después"
    assert not hecho["nuevo"] and Path(hecho["respaldo"]).read_text(encoding="utf-8") == "antes"


def test_python_runs_in_the_work_folder_and_returns_its_output(carpeta):
    hecho = ab.correr_python("print(sum([2, 3]))", str(carpeta / "trabajo"))

    assert hecho["codigo_de_salida"] == 0
    assert hecho["salida"].strip() == "5"
    assert hecho["programa"].startswith(str(carpeta / "trabajo"))


# --- Confirmación: la vigila el sistema, no el modelo ---


async def test_python_waits_for_a_yes_in_a_later_message(carpeta):
    confirmaciones = Confirmaciones()
    tools = herramientas(carpeta, confirmaciones)

    pedido = await tools["python_correr"].handler(
        {"equipo": "portatil", "codigo": "print('hola')", "para_que": "saludar"}
    )
    assert pedido.startswith("PENDIENTE #1")
    assert not list((carpeta / "trabajo").glob("*.py"))  # todavía no se corrió nada

    with pytest.raises(ValueError, match="pregúntale al usuario"):
        await tools["accion_confirmar"].handler({"numero": 1})

    confirmaciones.nuevo_turno()  # el usuario respondió
    resultado = json.loads(await tools["accion_confirmar"].handler({"numero": 1}))

    assert resultado["salida"].strip() == "hola"
    with pytest.raises(ValueError, match="no existe"):
        await tools["accion_confirmar"].handler({"numero": 1})  # una sola vez


async def test_unconfirmed_actions_expire(carpeta):
    confirmaciones = Confirmaciones()
    tools = herramientas(carpeta, confirmaciones)
    await tools["archivos_organizar"].handler(
        {"equipo": "portatil", "operacion": "papelera", "ruta": str(carpeta / "trabajo")}
    )

    for _ in range(4):
        confirmaciones.nuevo_turno()

    with pytest.raises(ValueError, match="venció"):
        await tools["accion_confirmar"].handler({"numero": 1})
    assert (carpeta / "trabajo").exists()


async def test_tools_edit_and_undo_through_the_laptop(carpeta):
    tools = herramientas(carpeta)
    archivo = carpeta / "config.json"
    archivo.write_text('{"modo": "simulacion"}', encoding="utf-8")

    await tools["archivo_editar"].handler(
        {"equipo": "portatil", "ruta": str(archivo), "buscar": "simulacion", "reemplazo": "real"}
    )
    assert archivo.read_text(encoding="utf-8") == '{"modo": "real"}'
    await tools["archivo_deshacer"].handler({"equipo": "portatil", "ruta": str(archivo)})
    assert archivo.read_text(encoding="utf-8") == '{"modo": "simulacion"}'

    with pytest.raises(ValueError, match="Equipos disponibles"):
        await tools["archivos_listar"].handler({"equipo": "optometria", "carpeta": str(carpeta)})


def test_every_file_and_code_tool_is_reserved_for_the_user(carpeta):
    assert set(herramientas(carpeta)) == SOLO_DEL_USUARIO


async def test_whatsapp_contacts_can_never_use_them(tmp_path):
    from azul.adapters.sqlite_store import SqliteStore
    from azul.core.whatsapp import Recepcionista

    store = SqliteStore(tmp_path / "azul.db")
    recepcionista = Recepcionista(object(), store, "573000000001")
    usadas = []

    async def editar(entrada):
        usadas.append(entrada)
        return "editado"

    await store.wa_agregar_regla("573000000002", "archivo_editar", "Puede editar todo")
    vigilada = recepcionista._envolver("573000000002")(ToolSpec("archivo_editar", "", {}, editar))

    respuesta = await vigilada.handler({"ruta": "C:\\x.py"})

    assert usadas == []  # ni siquiera con una regla
    assert "solo lo puede pedir el usuario" in respuesta


# --- El ayudante de Optometría también atiende /archivos ---


def test_the_helper_serves_files_with_the_same_rules(carpeta):
    from tests.test_correo_remoto import CLAVE, ayudante

    (carpeta / "a.txt").write_text("hola", encoding="utf-8")
    config = {"respaldos": str(carpeta / "r"), "trabajo": str(carpeta / "t"), "raices": []}
    servicios = {
        "/archivos": (
            lambda accion, entrada: ab.ejecutar(accion, entrada, config),
            ab.ACCIONES,
            ab.ArchivoError,
        )
    }

    def pedir(accion, entrada):
        cuerpo = json.dumps({"accion": accion, "entrada": entrada}).encode()
        return ayudante.atender("POST", "/archivos", CLAVE, cuerpo, CLAVE, servicios)

    codigo, datos = pedir("listar", {"carpeta": str(carpeta)})
    assert codigo == 200 and [e["nombre"] for e in datos["elementos"]] == ["trabajo", "a.txt"]
    assert pedir("leer", {"ruta": r"C:\Windows\win.ini"}) == (
        422,
        {"error": "Esa ruta está en una carpeta del sistema; no la toco."},
    )
