"""Comandos de mantenimiento para el usuario: respaldar y restaurar la memoria, cambiar la clave."""

import re
import secrets
import socket
import subprocess
import sys
from pathlib import Path

import httpx2

from azul.backup import (
    BackupError,
    create_backup,
    latest_backup,
    prune,
    read_manifest,
    restore_backup,
)
from azul.config import REPO_ROOT, get_settings

URL_AYUDANTE = "https://desktop-uqe8rug.tailc78da3.ts.net:8443"

# Sin letras que se confunden al escribirlas en el celular (l, 1, o, 0, i).
LETRAS_DE_CLAVE = "abcdefghjkmnpqrstuvwxyz23456789"


def respaldar() -> None:
    settings = get_settings()
    try:
        created = create_backup(settings.db_path, settings.backup_destinations)
    except BackupError as error:
        _fail(str(error))
    for path in created:
        prune(path.parent, settings.backups_to_keep)
        print(f"Respaldo guardado en: {path}")
    print("Listo. Tus claves (.env) no se incluyen en el respaldo.")


def restaurar() -> None:
    settings = get_settings()
    if _azul_is_running(settings.port):
        _fail("Azul está abierto. Ciérralo (cierra su ventana) y vuelve a intentarlo.")

    backup = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_backup(settings.backup_destinations)
    if backup is None:
        _fail("No encontré ningún respaldo.")
    try:
        manifest = read_manifest(backup)
    except BackupError as error:
        _fail(str(error))

    print(f"Respaldo: {backup}")
    print(f"  Creado: {manifest.get('creado', '?')}")
    print(f"  Mensajes: {manifest.get('mensajes', '?')}")
    print(f"  Datos sobre ti: {manifest.get('datos_del_usuario', '?')}")
    answer = input("¿Reemplazar la memoria actual por este respaldo? (s/n): ").strip().lower()
    if answer not in ("s", "si", "sí"):
        print("No se cambió nada.")
        return

    try:
        safety = restore_backup(backup, settings.db_path, safety_dir=settings.backup_dir)
    except BackupError as error:
        _fail(str(error))
    if safety:
        print(f"Por si acaso, la memoria anterior quedó guardada en: {safety}")
    print("Listo. Ya puedes abrir Azul de nuevo.")


def cambiar_clave(env: Path = REPO_ROOT / ".env") -> str:
    """Pone una clave de acceso nueva en .env y la devuelve (16 letras, ~79 bits)."""
    grupos = ["".join(secrets.choice(LETRAS_DE_CLAVE) for _ in range(4)) for _ in range(4)]
    clave = "-".join(grupos)
    poner_en_env(env, "AZUL_ACCESS_KEY", clave)
    return clave


def poner_en_env(env: Path, nombre: str, valor: str) -> None:
    """Cambia (o agrega) una variable en .env sin tocar las demás líneas."""
    texto = env.read_text(encoding="utf-8-sig") if env.exists() else ""
    linea = f"{nombre}={valor}"
    patron = rf"^{re.escape(nombre)}=.*$"
    if re.search(patron, texto, flags=re.M):
        texto = re.sub(patron, lambda _: linea, texto, count=1, flags=re.M)
    else:
        texto = texto.rstrip("\n") + ("\n" if texto else "") + linea + "\n"
    env.write_text(texto, encoding="utf-8")


def conectar_correo_optometria(env: Path = REPO_ROOT / ".env") -> None:
    """Conecta a Azul con el ayudante de Outlook del PC de Optometría (ADR 0040)."""
    print("Conectar a Azul con el Outlook del PC de Optometría.")
    print("Necesitas la clave que mostró el ayudante allá (está en ayudante-optometria\\.clave).")
    print()
    url = input(f"Dirección del ayudante [{URL_AYUDANTE}]: ").strip() or URL_AYUDANTE
    clave = input("Clave del ayudante: ").strip()
    if not clave:
        _fail("No escribiste la clave; no se cambió nada.")
    try:
        respuesta = httpx2.post(
            url.rstrip("/") + "/outlook",
            headers={"X-Azul-Clave": clave},
            json={"accion": "ping"},
            timeout=15,
        )
    except httpx2.HTTPError:
        _fail("No pude llegar al ayudante. ¿Está abierto en Optometría y con Tailscale serve?")
    if respuesta.status_code == 401:
        _fail("El ayudante respondió, pero la clave no coincide. No se cambió nada.")
    if respuesta.status_code != 200:
        _fail(f"El ayudante respondió algo inesperado ({respuesta.status_code}).")
    poner_en_env(env, "AZUL_CORREO_REMOTO_URL", url)
    poner_en_env(env, "AZUL_CORREO_REMOTO_CLAVE", clave)
    print()
    print("Listo: el ayudante respondió y quedó guardado en .env.")
    print("Cierra la ventana negra de Azul y abre otra vez 'Iniciar Azul'.")


def cambiar_clave_y_mostrar() -> None:
    clave = cambiar_clave()
    # Se muestra solo en esta ventana y se copia al portapapeles; no queda en ningún registro.
    subprocess.run(["clip"], input=clave.encode("ascii"), check=False)
    print("Clave de acceso nueva de Azul (ya quedó copiada; puedes pegarla con Ctrl+V):")
    print()
    print(f"    {clave}")
    print()
    print("1. Cierra la ventana negra de Azul y abre otra vez 'Iniciar Azul'.")
    print("2. En el celular, abre Azul: te pedirá la clave una vez. Escribe la nueva.")
    print("   (Los guiones no importan si los escribes igual que aquí.)")
    print("3. Si usas el atajo de Siri con la clave, cámbiala también ahí.")


def _azul_is_running(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)
