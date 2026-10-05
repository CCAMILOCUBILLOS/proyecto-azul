import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime

import pytest

from azul.adapters.sqlite_store import SqliteStore
from azul.backup import (
    PREFIX,
    SAFETY_PREFIX,
    BackupError,
    backup_if_due,
    create_backup,
    latest_backup,
    prune,
    read_manifest,
    restore_backup,
)
from azul.core.ports import Fact, Message

pytestmark = pytest.mark.anyio


def at(day, hour=9):
    return lambda: datetime(2026, 10, day, hour, 0, 0)


@pytest.fixture
async def memory(tmp_path):
    db_path = tmp_path / "datos" / "azul.db"
    store = SqliteStore(db_path)
    await store.add_message(Message("user", "Hola, me llamo Camilo."))
    await store.add_message(Message("assistant", "¡Hola, Camilo!"))
    await store.add_fact(Fact("El usuario se llama Camilo."))
    return db_path, store


async def test_backup_and_restore_keep_the_memory_intact(tmp_path, memory):
    db_path, store = memory
    [backup] = create_backup(db_path, [tmp_path / "respaldos"], now=at(5))

    # Después del respaldo, la memoria cambia (o se pierde).
    await store.add_fact(Fact("Dato que no estaba en el respaldo."))
    restore_backup(backup, db_path, safety_dir=tmp_path / "respaldos", now=at(6))

    restored = SqliteStore(db_path)
    assert [m.text for m in await restored.recent_messages(10)] == [
        "Hola, me llamo Camilo.",
        "¡Hola, Camilo!",
    ]
    assert [f.text for f in await restored.facts()] == ["El usuario se llama Camilo."]


async def test_restore_keeps_a_safety_copy_of_the_current_memory(tmp_path, memory):
    db_path, store = memory
    [backup] = create_backup(db_path, [tmp_path / "respaldos"], now=at(5))
    await store.add_fact(Fact("Dato nuevo."))

    safety = restore_backup(backup, db_path, safety_dir=tmp_path / "respaldos", now=at(6))

    assert safety.name.startswith(SAFETY_PREFIX)
    assert read_manifest(safety)["datos_del_usuario"] == 2


async def test_restore_works_on_a_new_computer(tmp_path, memory):
    db_path, _ = memory
    [backup] = create_backup(db_path, [tmp_path / "respaldos"], now=at(5))
    new_db = tmp_path / "otro-pc" / "datos" / "azul.db"

    assert restore_backup(backup, new_db, safety_dir=tmp_path / "otro-pc") is None
    assert len(await SqliteStore(new_db).recent_messages(10)) == 2


async def test_backup_goes_to_every_destination_with_a_manifest(tmp_path, memory):
    db_path, _ = memory

    created = create_backup(db_path, [tmp_path / "local", tmp_path / "onedrive"], now=at(5))

    assert [p.parent.name for p in created] == ["local", "onedrive"]
    assert created[0].name == f"{PREFIX}2026-10-05_090000.zip"
    manifest = read_manifest(created[1])
    assert manifest["mensajes"] == 2
    assert manifest["datos_del_usuario"] == 1
    with zipfile.ZipFile(created[0]) as archive:
        assert sorted(archive.namelist()) == ["azul.db", "manifiesto.json"]


async def test_one_broken_destination_does_not_stop_the_others(tmp_path, memory):
    db_path, _ = memory
    not_a_folder = tmp_path / "archivo"
    not_a_folder.write_text("no soy una carpeta")

    created = create_backup(db_path, [not_a_folder, tmp_path / "local"], now=at(5))

    assert [p.parent.name for p in created] == ["local"]


async def test_daily_backup_runs_once_per_day_and_keeps_the_latest(tmp_path, memory):
    db_path, _ = memory
    folder = tmp_path / "respaldos"

    for day in range(1, 6):
        assert backup_if_due(db_path, [folder], keep=3, now=at(day))
        assert backup_if_due(db_path, [folder], keep=3, now=at(day, hour=18)) == []

    names = sorted(p.name for p in folder.iterdir())
    assert names == [f"{PREFIX}2026-10-0{d}_090000.zip" for d in (3, 4, 5)]
    assert latest_backup([folder]).name == f"{PREFIX}2026-10-05_090000.zip"


def test_prune_ignores_other_files(tmp_path):
    (tmp_path / "notas.txt").write_text("mío")
    for day in (1, 2, 3):
        (tmp_path / f"{PREFIX}2026-10-0{day}_090000.zip").write_bytes(b"")

    prune(tmp_path, keep=1)

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        f"{PREFIX}2026-10-03_090000.zip",
        "notas.txt",
    ]


def test_invalid_file_is_rejected(tmp_path):
    fake = tmp_path / "no-es-respaldo.zip"
    fake.write_bytes(b"cualquier cosa")

    with pytest.raises(BackupError, match="no es un respaldo"):
        restore_backup(fake, tmp_path / "azul.db", safety_dir=tmp_path)


async def test_backup_from_a_newer_version_is_rejected(tmp_path, memory):
    db_path, _ = memory
    backup = tmp_path / f"{PREFIX}del-futuro.zip"
    with zipfile.ZipFile(backup, "w") as archive:
        archive.write(db_path, "azul.db")
        archive.writestr("manifiesto.json", json.dumps({"version_esquema": 999}))

    with pytest.raises(BackupError, match="más nueva"):
        restore_backup(backup, db_path, safety_dir=tmp_path)

    with closing(sqlite3.connect(db_path)) as db:  # la memoria actual no se tocó
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2


def test_nothing_to_back_up_yet(tmp_path):
    with pytest.raises(BackupError, match="no hay memoria"):
        create_backup(tmp_path / "no-existe.db", [tmp_path])
