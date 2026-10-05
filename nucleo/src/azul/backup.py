"""Respaldo y restauración de la memoria de Azul (R1, ADR 0016, ADR 0022).

Un respaldo es un .zip con una copia consistente de la base de datos (hecha con
la API de respaldo de SQLite, válida aunque Azul esté funcionando) y un
manifiesto. Las claves (.env) no se incluyen nunca.
"""

import json
import logging
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Callable
from contextlib import closing
from datetime import datetime
from pathlib import Path

from azul.adapters.sqlite_store import SCHEMA_VERSION

log = logging.getLogger(__name__)

PREFIX = "azul-respaldo-"
SAFETY_PREFIX = "azul-antes-de-restaurar-"
DB_NAME = "azul.db"
MANIFEST_NAME = "manifiesto.json"
MANIFEST_FORMAT = 1


class BackupError(Exception):
    """Problema con un respaldo, con un mensaje apto para el usuario."""


def create_backup(
    db_path: Path,
    destinations: list[Path],
    *,
    prefix: str = PREFIX,
    now: Callable[[], datetime] = datetime.now,
) -> list[Path]:
    """Crea el mismo respaldo en cada destino. Devuelve las rutas creadas."""
    if not db_path.exists():
        raise BackupError("Todavía no hay memoria que respaldar.")
    moment = now()
    name = f"{prefix}{moment:%Y-%m-%d_%H%M%S}.zip"
    created: list[Path] = []
    with tempfile.TemporaryDirectory() as work:
        copy = Path(work) / DB_NAME
        with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(copy)) as target:
            source.backup(target)
        manifest = {"formato": MANIFEST_FORMAT, "creado": moment.isoformat(), **_summary(copy)}
        for destination in destinations:
            try:
                destination.mkdir(parents=True, exist_ok=True)
                path = destination / name
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                    archive.write(copy, DB_NAME)
                    archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False))
                created.append(path)
            except OSError as error:
                # Un destino caído (p. ej. OneDrive desconectado) no impide los demás.
                log.error("No se pudo guardar el respaldo en %s: %s", destination, error)
    if not created:
        raise BackupError("No se pudo guardar el respaldo en ningún destino.")
    return created


def prune(destination: Path, keep: int, *, prefix: str = PREFIX) -> list[Path]:
    """Borra los respaldos más antiguos de un destino y deja los `keep` más recientes."""
    backups = sorted(destination.glob(f"{prefix}*.zip"))
    removed = backups[:-keep] if keep > 0 else backups
    for path in removed:
        path.unlink()
    return removed


def backup_if_due(
    db_path: Path,
    destinations: list[Path],
    *,
    keep: int,
    now: Callable[[], datetime] = datetime.now,
) -> list[Path]:
    """Respaldo automático: uno por día como máximo (se llama al iniciar Azul)."""
    if not db_path.exists():
        return []
    today = f"{PREFIX}{now():%Y-%m-%d}_"
    if any(any(d.glob(f"{today}*.zip")) for d in destinations if d.is_dir()):
        return []
    created = create_backup(db_path, destinations, now=now)
    for destination in destinations:
        if destination.is_dir():
            prune(destination, keep)
    return created


def latest_backup(destinations: list[Path]) -> Path | None:
    candidates = [p for d in destinations if d.is_dir() for p in d.glob(f"{PREFIX}*.zip")]
    return max(candidates, key=lambda p: p.name, default=None)


def read_manifest(backup: Path) -> dict:
    try:
        with zipfile.ZipFile(backup) as archive:
            return json.loads(archive.read(MANIFEST_NAME))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise BackupError(f"El archivo {backup.name} no es un respaldo válido de Azul.") from error


def restore_backup(
    backup: Path,
    db_path: Path,
    *,
    safety_dir: Path,
    now: Callable[[], datetime] = datetime.now,
) -> Path | None:
    """Reemplaza la memoria actual por la del respaldo.

    Antes guarda una copia de seguridad de la memoria actual en `safety_dir` y
    devuelve su ruta (o None si no había memoria). Azul debe estar cerrado.
    """
    manifest = read_manifest(backup)
    if manifest.get("version_esquema", 0) > SCHEMA_VERSION:
        raise BackupError("Ese respaldo viene de una versión más nueva de Azul. Actualiza primero.")

    with tempfile.TemporaryDirectory() as work:
        extracted = Path(work) / DB_NAME
        try:
            with zipfile.ZipFile(backup) as archive, open(extracted, "wb") as target:
                target.write(archive.read(DB_NAME))
        except (OSError, KeyError, zipfile.BadZipFile) as error:
            raise BackupError(f"No pude leer la memoria dentro de {backup.name}.") from error
        with closing(sqlite3.connect(extracted)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError(f"La memoria dentro de {backup.name} está dañada.")

        safety = None
        if db_path.exists():
            safety = create_backup(db_path, [safety_dir], prefix=SAFETY_PREFIX, now=now)[0]
        for suffix in ("", "-wal", "-shm"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(extracted, db_path)
    return safety


def _summary(db_path: Path) -> dict:
    with closing(sqlite3.connect(db_path)) as db:
        return {
            "version_esquema": db.execute("PRAGMA user_version").fetchone()[0],
            "mensajes": db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
            "datos_del_usuario": db.execute("SELECT COUNT(*) FROM facts").fetchone()[0],
        }
