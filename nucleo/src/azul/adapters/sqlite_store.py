"""Memoria y medidor de gasto en SQLite: un solo archivo en datos/ (ADR 0009, R1)."""

import asyncio
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azul.core.ports import Fact, Message, Pendiente, Regla, Usage

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
-- WhatsApp (ADR 0038). Tablas nuevas: IF NOT EXISTS basta, sin migración.
CREATE TABLE IF NOT EXISTS wa_vistos (id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wa_contactos (
    numero TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    ultimo_mensaje TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wa_mensajes (
    id INTEGER PRIMARY KEY,
    contacto TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    text TEXT NOT NULL,
    consulted TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS wa_mensajes_contacto ON wa_mensajes (contacto, id);
CREATE TABLE IF NOT EXISTS wa_datos (
    id INTEGER PRIMARY KEY,
    contacto TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (contacto, text)
);
CREATE TABLE IF NOT EXISTS wa_reglas (
    id INTEGER PRIMARY KEY,
    contacto TEXT NOT NULL,
    herramienta TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- Correos clasificados e itinerario (ADR 0039).
CREATE TABLE IF NOT EXISTS correo_clasificados (
    numero INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    de TEXT NOT NULL,
    asunto TEXT NOT NULL,
    recibido TEXT NOT NULL,
    prioridad TEXT NOT NULL,
    accion TEXT NOT NULL,
    fecha_limite TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'abierto',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS correo_reglas (
    id INTEGER PRIMARY KEY,
    criterio TEXT NOT NULL,
    prioridad TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS correo_preguntas (
    id INTEGER PRIMARY KEY,
    numero INTEGER NOT NULL,
    pregunta TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'abierta',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS correo_estado (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
-- Atajos que Azul aprendió para hacer órdenes sin Claude (ADR 0042).
CREATE TABLE IF NOT EXISTS atajos (
    frase TEXT PRIMARY KEY,
    herramienta TEXT NOT NULL,
    entrada TEXT NOT NULL,
    usos INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wa_pendientes (
    id INTEGER PRIMARY KEY,
    contacto TEXT NOT NULL,
    tipo TEXT NOT NULL,
    texto TEXT NOT NULL,
    propuesta TEXT NOT NULL,
    herramienta TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'abierto',
    created_at TEXT NOT NULL
);
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

    # --- WhatsApp (ADR 0038) ---

    async def wa_marcar_visto(self, id_mensaje: str) -> bool:
        nuevo = await self._write(
            "INSERT OR IGNORE INTO wa_vistos (id, created_at) VALUES (?, ?)",
            (id_mensaje, self._timestamp()),
        )
        return nuevo == 1

    async def wa_guardar_contacto(self, numero: str, nombre: str) -> None:
        await self._write(
            "INSERT INTO wa_contactos (numero, nombre, ultimo_mensaje) VALUES (?, ?, ?) "
            "ON CONFLICT (numero) DO UPDATE SET "
            "nombre = COALESCE(NULLIF(excluded.nombre, ''), nombre), "
            "ultimo_mensaje = excluded.ultimo_mensaje",
            (numero, nombre, self._timestamp()),
        )

    async def wa_contactos(self) -> list[dict[str, Any]]:
        rows = await self._read(
            "SELECT numero, nombre, ultimo_mensaje FROM wa_contactos ORDER BY ultimo_mensaje DESC",
            (),
        )
        return [{"numero": n, "nombre": nombre, "ultimo_mensaje": u} for n, nombre, u in rows]

    async def wa_ultimo_mensaje(self, numero: str) -> datetime | None:
        rows = await self._read(
            "SELECT ultimo_mensaje FROM wa_contactos WHERE numero = ?", (numero,)
        )
        return datetime.fromisoformat(rows[0][0]) if rows else None

    async def wa_reglas(self, contacto: str | None = None) -> list[Regla]:
        sql = "SELECT id, contacto, herramienta, descripcion FROM wa_reglas"
        if contacto:
            rows = await self._read(sql + " WHERE contacto = ? ORDER BY id", (contacto,))
        else:
            rows = await self._read(sql + " ORDER BY contacto, id", ())
        return [Regla(*row) for row in rows]

    async def wa_agregar_regla(self, contacto: str, herramienta: str, descripcion: str) -> int:
        return await self._insert(
            "INSERT INTO wa_reglas (contacto, herramienta, descripcion, created_at) "
            "VALUES (?, ?, ?, ?)",
            (contacto, herramienta, descripcion, self._timestamp()),
        )

    async def wa_borrar_regla(self, id_regla: int) -> bool:
        return await self._write("DELETE FROM wa_reglas WHERE id = ?", (id_regla,)) == 1

    async def wa_nuevo_pendiente(self, pendiente: Pendiente) -> int:
        return await self._insert(
            "INSERT INTO wa_pendientes "
            "(contacto, tipo, texto, propuesta, herramienta, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                pendiente.contacto,
                pendiente.tipo,
                pendiente.texto,
                pendiente.propuesta,
                pendiente.herramienta,
                self._timestamp(),
            ),
        )

    async def wa_pendientes(self) -> list[Pendiente]:
        rows = await self._read(
            "SELECT id, contacto, tipo, texto, propuesta, herramienta FROM wa_pendientes "
            "WHERE estado = 'abierto' ORDER BY id",
            (),
        )
        return [Pendiente(*row) for row in rows]

    async def wa_cerrar_pendiente(self, id_pendiente: int, estado: str) -> Pendiente | None:
        rows = await self._read(
            "SELECT id, contacto, tipo, texto, propuesta, herramienta FROM wa_pendientes "
            "WHERE id = ? AND estado = 'abierto'",
            (id_pendiente,),
        )
        if not rows:
            return None
        await self._write(
            "UPDATE wa_pendientes SET estado = ? WHERE id = ?", (estado, id_pendiente)
        )
        return Pendiente(*rows[0])

    # --- Atajos de órdenes directas (ADR 0042) ---

    async def atajo_buscar(self, frase: str) -> tuple[str, dict[str, Any]] | None:
        rows = await self._read("SELECT herramienta, entrada FROM atajos WHERE frase = ?", (frase,))
        if not rows:
            return None
        await self._write("UPDATE atajos SET usos = usos + 1 WHERE frase = ?", (frase,))
        return str(rows[0][0]), json.loads(rows[0][1])

    async def atajo_guardar(self, frase: str, herramienta: str, entrada: dict[str, Any]) -> None:
        await self._write(
            "INSERT INTO atajos (frase, herramienta, entrada, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (frase) DO UPDATE SET herramienta = excluded.herramienta, "
            "entrada = excluded.entrada",
            (frase, herramienta, json.dumps(entrada, ensure_ascii=False), self._timestamp()),
        )

    # --- Bandeja de correo (ADR 0039) ---

    async def bandeja_ya_vistos(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        marcas = ",".join("?" * len(ids))
        rows = await self._read(
            f"SELECT id FROM correo_clasificados WHERE id IN ({marcas})", tuple(ids)
        )
        return {row[0] for row in rows}

    async def bandeja_guardar(self, clasificados: list[dict[str, Any]]) -> None:
        ahora = self._timestamp()

        def run() -> None:
            with closing(self._connect()) as db, db:
                db.executemany(
                    "INSERT OR IGNORE INTO correo_clasificados (id, de, asunto, recibido, "
                    "prioridad, accion, fecha_limite, estado, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            c["id"],
                            c.get("de", ""),
                            c.get("asunto", ""),
                            c.get("fecha", ""),
                            c["prioridad"],
                            c.get("accion", ""),
                            c.get("fecha_limite", ""),
                            c.get("estado", "abierto"),
                            ahora,
                        )
                        for c in clasificados
                    ],
                )

        await asyncio.to_thread(run)

    async def bandeja_numero(self, id_correo: str) -> int | None:
        rows = await self._read("SELECT numero FROM correo_clasificados WHERE id = ?", (id_correo,))
        return int(rows[0][0]) if rows else None

    async def bandeja_itinerario(self, limite: int) -> list[dict[str, Any]]:
        rows = await self._read(
            "SELECT numero, de, asunto, recibido, prioridad, accion, fecha_limite "
            "FROM correo_clasificados WHERE estado = 'abierto' AND prioridad != 'baja' "
            "ORDER BY CASE prioridad WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1 ELSE 2 END, "
            "CASE fecha_limite WHEN '' THEN '9999' ELSE fecha_limite END, recibido DESC LIMIT ?",
            (limite,),
        )
        campos = ("numero", "de", "asunto", "recibido", "prioridad", "accion", "fecha_limite")
        return [dict(zip(campos, row, strict=True)) for row in rows]

    async def bandeja_marcar(self, numero: int, estado: str) -> bool:
        cambiados = await self._write(
            "UPDATE correo_clasificados SET estado = ? WHERE numero = ?", (estado, numero)
        )
        return cambiados == 1

    async def bandeja_cambiar_prioridad(self, numero: int, prioridad: str) -> dict[str, Any] | None:
        await self._write(
            "UPDATE correo_clasificados SET prioridad = ? WHERE numero = ?", (prioridad, numero)
        )
        rows = await self._read(
            "SELECT id, de, asunto FROM correo_clasificados WHERE numero = ?", (numero,)
        )
        return {"id": rows[0][0], "de": rows[0][1], "asunto": rows[0][2]} if rows else None

    async def bandeja_reglas(self) -> list[dict[str, Any]]:
        rows = await self._read("SELECT id, criterio, prioridad FROM correo_reglas ORDER BY id", ())
        return [{"id": i, "criterio": c, "prioridad": p} for i, c, p in rows]

    async def bandeja_agregar_regla(self, criterio: str, prioridad: str) -> int:
        return await self._insert(
            "INSERT INTO correo_reglas (criterio, prioridad, created_at) VALUES (?, ?, ?)",
            (criterio, prioridad, self._timestamp()),
        )

    async def bandeja_borrar_regla(self, id_regla: int) -> bool:
        return await self._write("DELETE FROM correo_reglas WHERE id = ?", (id_regla,)) == 1

    async def bandeja_nueva_pregunta(self, numero: int, pregunta: str) -> int:
        return await self._insert(
            "INSERT INTO correo_preguntas (numero, pregunta, created_at) VALUES (?, ?, ?)",
            (numero, pregunta, self._timestamp()),
        )

    async def bandeja_preguntas(self) -> list[dict[str, Any]]:
        rows = await self._read(
            "SELECT p.id, p.numero, p.pregunta, c.de, c.asunto, c.prioridad "
            "FROM correo_preguntas p JOIN correo_clasificados c ON c.numero = p.numero "
            "WHERE p.estado = 'abierta' ORDER BY p.id",
            (),
        )
        campos = ("id", "numero", "pregunta", "de", "asunto", "prioridad")
        return [dict(zip(campos, row, strict=True)) for row in rows]

    async def bandeja_cerrar_pregunta(self, id_pregunta: int) -> dict[str, Any] | None:
        rows = await self._read(
            "SELECT id, numero, pregunta FROM correo_preguntas WHERE id = ? AND estado = 'abierta'",
            (id_pregunta,),
        )
        if not rows:
            return None
        await self._write(
            "UPDATE correo_preguntas SET estado = 'respondida' WHERE id = ?", (id_pregunta,)
        )
        return {"id": rows[0][0], "numero": rows[0][1], "pregunta": rows[0][2]}

    async def bandeja_estado(self, clave: str) -> str | None:
        rows = await self._read("SELECT valor FROM correo_estado WHERE clave = ?", (clave,))
        return str(rows[0][0]) if rows else None

    async def bandeja_guardar_estado(self, clave: str, valor: str) -> None:
        await self._write(
            "INSERT INTO correo_estado (clave, valor) VALUES (?, ?) "
            "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
            (clave, valor),
        )

    def memoria_de(self, contacto: str) -> "MemoriaDeContacto":
        return MemoriaDeContacto(self, contacto)

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

    async def _insert(self, sql: str, params: tuple[Any, ...]) -> int:
        def run() -> int:
            with closing(self._connect()) as db, db:
                return int(db.execute(sql, params).lastrowid or 0)

        return await asyncio.to_thread(run)

    async def _read(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        def run() -> list[tuple[Any, ...]]:
            with closing(self._connect()) as db:
                return db.execute(sql, params).fetchall()

        return await asyncio.to_thread(run)


class MemoriaDeContacto:
    """La conversación de WhatsApp con un contacto (ADR 0038).

    Su historial es aparte del del usuario. Los datos que ve son los del usuario
    (solo lectura) más lo que Azul aprendió de ese contacto.
    """

    def __init__(self, store: SqliteStore, contacto: str) -> None:
        self._store = store
        self._contacto = contacto

    async def add_message(self, message: Message) -> None:
        await self._store._write(
            "INSERT INTO wa_mensajes (contacto, role, text, consulted, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                self._contacto,
                message.role,
                message.text,
                message.consulted,
                self._store._timestamp(),
            ),
        )

    async def recent_messages(self, limit: int) -> list[Message]:
        rows = await self._store._read(
            "SELECT role, text, created_at, consulted FROM wa_mensajes WHERE contacto = ? "
            "ORDER BY id DESC LIMIT ?",
            (self._contacto, limit),
        )
        return [
            Message(role, text, datetime.fromisoformat(at), consulted)
            for role, text, at, consulted in reversed(rows)
        ]

    async def message_count(self) -> int:
        rows = await self._store._read(
            "SELECT COUNT(*) FROM wa_mensajes WHERE contacto = ?", (self._contacto,)
        )
        return int(rows[0][0])

    async def add_fact(self, fact: Fact) -> bool:
        nuevo = await self._store._write(
            "INSERT OR IGNORE INTO wa_datos (contacto, text, created_at) VALUES (?, ?, ?)",
            (self._contacto, fact.text, self._store._timestamp()),
        )
        return nuevo == 1

    async def facts(self) -> list[Fact]:
        del_contacto = await self._store._read(
            "SELECT text, created_at FROM wa_datos WHERE contacto = ? ORDER BY id",
            (self._contacto,),
        )
        return [
            *await self._store.facts(),
            *(
                Fact(f"(Sobre este contacto) {text}", datetime.fromisoformat(at))
                for text, at in del_contacto
            ),
        ]

    async def corregir_ultima_respuesta(self, texto: str | None) -> None:
        rows = await self._store._read(
            "SELECT id FROM wa_mensajes WHERE contacto = ? AND role = 'assistant' "
            "ORDER BY id DESC LIMIT 1",
            (self._contacto,),
        )
        if not rows:
            return
        if texto is None:
            await self._store._write("DELETE FROM wa_mensajes WHERE id = ?", (rows[0][0],))
        else:
            await self._store._write(
                "UPDATE wa_mensajes SET text = ? WHERE id = ?", (texto, rows[0][0])
            )
