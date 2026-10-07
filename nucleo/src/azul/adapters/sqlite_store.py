"""Memoria y medidor de gasto en SQLite: un solo archivo en datos/ (ADR 0009, R1)."""

import asyncio
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azul.core.ports import Fact, Message, Usage

# Súbelo y agrega una migración en _MIGRATIONS cuando cambie el esquema.
SCHEMA_VERSION = 2

# Migración de la versión N-1 a la N. Se aplican en orden al abrir la base, así
# un respaldo viejo restaurado se actualiza solo (R1).
_MIGRATIONS = {
    # v2: qué consultó Azul para cada respuesta (búsqueda web, clima…), para que
    # en turnos siguientes sepa que sí lo consultó (ADR 0027).
    2: "ALTER TABLE messages ADD COLUMN consulted TEXT NOT NULL DEFAULT ''",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    cost_usd REAL NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_created_at ON usage (created_at);
"""


class SqliteStore:
    """Cumple los puertos MemoryStore y UsageMeter sobre el mismo archivo."""

    def __init__(self, path: Path, now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._path = path
        self._now = now
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.executescript(_SCHEMA)
            version = max(1, db.execute("PRAGMA user_version").fetchone()[0])
            for target in range(version + 1, SCHEMA_VERSION + 1):
                db.execute(_MIGRATIONS[target])
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # --- MemoryStore ---

    async def add_message(self, message: Message) -> None:
        await self._write(
            "INSERT INTO messages (role, text, consulted, created_at) VALUES (?, ?, ?, ?)",
            (message.role, message.text, message.consulted, self._timestamp()),
        )

    async def recent_messages(self, limit: int) -> list[Message]:
        rows = await self._read(
            "SELECT role, text, created_at, consulted FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [
            Message(role, text, datetime.fromisoformat(at), consulted)
            for role, text, at, consulted in reversed(rows)
        ]

    async def message_count(self) -> int:
        rows = await self._read("SELECT COUNT(*) FROM messages", ())
        return int(rows[0][0])

    async def add_fact(self, fact: Fact) -> bool:
        inserted = await self._write(
            "INSERT OR IGNORE INTO facts (text, created_at) VALUES (?, ?)",
            (fact.text, self._timestamp()),
        )
        return inserted == 1

    async def facts(self) -> list[Fact]:
        rows = await self._read("SELECT text, created_at FROM facts ORDER BY id", ())
        return [Fact(text, datetime.fromisoformat(at)) for text, at in rows]

    # --- UsageMeter ---

    async def record(self, usage: Usage) -> None:
        await self._write(
            "INSERT INTO usage (provider, cost_usd, detail, created_at) VALUES (?, ?, ?, ?)",
            (usage.provider, usage.cost_usd, usage.detail, self._timestamp()),
        )

    async def month_total_usd(self) -> float:
        # El mes se cuenta en la hora local del usuario.
        local_now = self._now().astimezone()
        month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rows = await self._read(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM usage WHERE created_at >= ?",
            (month_start.astimezone(UTC).isoformat(),),
        )
        return float(rows[0][0])

    # --- Interno ---

    def _timestamp(self) -> str:
        return self._now().astimezone(UTC).isoformat()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    async def _write(self, sql: str, params: tuple[Any, ...]) -> int:
        def run() -> int:
            with closing(self._connect()) as db, db:
                return db.execute(sql, params).rowcount

        return await asyncio.to_thread(run)

    async def _read(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        def run() -> list[tuple[Any, ...]]:
            with closing(self._connect()) as db:
                return db.execute(sql, params).fetchall()

        return await asyncio.to_thread(run)
