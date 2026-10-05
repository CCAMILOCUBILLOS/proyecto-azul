"""Comandos de mantenimiento para el usuario: respaldar y restaurar la memoria."""

import socket
import sys
from pathlib import Path

from azul.backup import (
    BackupError,
    create_backup,
    latest_backup,
    prune,
    read_manifest,
    restore_backup,
)
from azul.config import get_settings


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


def _azul_is_running(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)
