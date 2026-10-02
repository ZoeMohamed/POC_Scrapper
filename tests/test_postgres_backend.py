from __future__ import annotations

import asyncio

from app.config import Settings
import pytest

from app.db_postgres import (
    POSTGRES_SCHEMA,
    PostgresDatabase,
    _Cursor,
    _PoolConnection,
    _postgres_query,
    _rowcount,
)


def test_postgres_query_converts_qmark_placeholders() -> None:
    assert _postgres_query("SELECT * FROM topics WHERE id=? AND status=?") == (
        "SELECT * FROM topics WHERE id=$1 AND status=$2"
    )


def test_asyncpg_command_status_rowcount() -> None:
    assert _rowcount("INSERT 0 1") == 1
    assert _rowcount("UPDATE 12") == 12
    assert _rowcount("DELETE 0") == 0


def test_supabase_schema_is_private_and_indexed() -> None:
    assert "CREATE SCHEMA IF NOT EXISTS scraper" in POSTGRES_SCHEMA
    assert "REVOKE ALL ON SCHEMA scraper FROM PUBLIC, anon, authenticated" in POSTGRES_SCHEMA
    assert "ALTER TABLE scraper.social_posts ENABLE ROW LEVEL SECURITY" in POSTGRES_SCHEMA
    assert "idx_social_posts_topic" in POSTGRES_SCHEMA
    assert "idx_comments_pending" in POSTGRES_SCHEMA
    assert "comments_pkey PRIMARY KEY (row_key)" in POSTGRES_SCHEMA
    assert "idx_places_topic_id" in POSTGRES_SCHEMA


def test_database_backend_auto_configuration() -> None:
    settings = Settings(
        database_backend="auto",
        supabase_db_url="postgresql://example.invalid/postgres",
    )
    assert settings.database_backend == "auto"
    assert settings.supabase_db_url.startswith("postgresql://")
    assert settings.database_auto_migrate is False


@pytest.mark.asyncio
async def test_postgres_writes_share_transaction_until_commit() -> None:
    class Transaction:
        started = False
        committed = False

        async def start(self) -> None:
            self.started = True

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            pass

    class Connection:
        def __init__(self) -> None:
            self.tx = Transaction()
            self.queries: list[tuple[str, tuple[object, ...]]] = []

        def transaction(self) -> Transaction:
            return self.tx

        async def execute(self, query: str, *values: object) -> str:
            self.queries.append((query, values))
            return "UPDATE 1"

    class Pool:
        def __init__(self) -> None:
            self.connection = Connection()
            self.acquires = 0
            self.releases = 0

        async def acquire(self) -> Connection:
            self.acquires += 1
            return self.connection

        async def release(self, connection: Connection) -> None:
            assert connection is self.connection
            self.releases += 1

    pool = Pool()
    adapter = _PoolConnection(pool)
    await adapter.execute("UPDATE topics SET status=? WHERE id=?", ("active", "kopi"))
    await adapter.execute("UPDATE topics SET is_active=? WHERE id=?", (1, "kopi"))
    assert pool.acquires == 1
    assert pool.connection.tx.started is True
    assert pool.releases == 0

    await adapter.commit()
    assert pool.connection.tx.committed is True
    assert pool.releases == 1


@pytest.mark.asyncio
async def test_select_keeps_result_when_pool_release_times_out() -> None:
    class Connection:
        async def fetch(self, query: str, *values: object) -> list[dict[str, object]]:
            return [{"value": 7}]

    class Pool:
        connection = Connection()

        async def acquire(self, *, timeout: int) -> Connection:
            return self.connection

        async def release(self, connection: Connection, *, timeout: int) -> None:
            raise asyncio.TimeoutError

    cursor = await _PoolConnection(Pool()).execute("SELECT ? AS value", (7,))
    assert await cursor.fetchone() == {"value": 7}


@pytest.mark.asyncio
async def test_social_failure_condition_is_bound_as_boolean() -> None:
    class Adapter:
        params: tuple[object, ...] = ()

        async def execute(self, sql: str, params: tuple[object, ...]) -> _Cursor:
            self.params = params
            return _Cursor(rowcount=1)

        async def commit(self) -> None:
            pass

    database = PostgresDatabase("postgresql://example.invalid/postgres")
    adapter = Adapter()
    database._adapter = adapter
    await database.mark_social_sentiment_attempt(
        platform="facebook", post_id="post-1", topic_id="topik", failed=True
    )
    assert adapter.params[0] is True
