import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest

from azul.adapters.sqlite_store import SCHEMA_VERSION, SqliteStore
from azul.core.ports import Fact, Message, Usage

pytestmark = pytest.mark.anyio


class Clock:
    def __init__(self, moment: datetime):
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


@pytest.fixture
def clock():
    return Clock(datetime(2026, 10, 15, 12, 0, tzinfo=UTC))


@pytest.fixture
def store(tmp_path, clock):
    return SqliteStore(tmp_path / "datos" / "azul.db", now=clock)


async def test_messages_keep_order_and_limit(store):
    for text in ("uno", "dos", "tres"):
        await store.add_message(Message("user", text))

    recent = await store.recent_messages(2)

    assert [m.text for m in recent] == ["dos", "tres"]
    assert recent[0].created_at == datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


async def test_facts_are_not_duplicated(store):
    assert await store.add_fact(Fact("Le gusta el café sin azúcar."))
    assert not await store.add_fact(Fact("Le gusta el café sin azúcar."))

    assert [f.text for f in await store.facts()] == ["Le gusta el café sin azúcar."]


async def test_month_total_only_counts_current_month(store, clock):
    clock.moment = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    await store.record(Usage("anthropic", 3.0))
    clock.moment = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    await store.record(Usage("anthropic", 0.25))
    await store.record(Usage("anthropic", 0.5))

    assert await store.month_total_usd() == pytest.approx(0.75)


async def test_data_survives_reopening(tmp_path, clock):
    path = tmp_path / "azul.db"
    await SqliteStore(path, now=clock).add_fact(Fact("Se llama Azul su asistente."))

    reopened = SqliteStore(path, now=clock)

    assert [f.text for f in await reopened.facts()] == ["Se llama Azul su asistente."]


def test_schema_version_is_recorded(store, tmp_path):
    with closing(sqlite3.connect(tmp_path / "datos" / "azul.db")) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
