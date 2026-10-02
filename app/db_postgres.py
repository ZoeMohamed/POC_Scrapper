"""Supabase Postgres backend compatible with the existing Database helpers.

The scraper tables live in a private ``scraper`` schema. They are intentionally
not exposed through Supabase's Data API; the FastAPI server is the only runtime
that needs database access.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
from typing import Any, Iterable, Sequence

from app.db import Database


logger = logging.getLogger(__name__)


POSTGRES_SCHEMA = """
CREATE SCHEMA IF NOT EXISTS scraper;
REVOKE ALL ON SCHEMA scraper FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS scraper.topics (
    id text PRIMARY KEY,
    name text NOT NULL,
    category text NOT NULL DEFAULT 'umum',
    keywords text NOT NULL,
    product_terms text NOT NULL DEFAULT '[]',
    exclude_terms text NOT NULL DEFAULT '[]',
    cities text NOT NULL,
    own_place_id text,
    status text NOT NULL DEFAULT 'discovering',
    is_seed smallint NOT NULL DEFAULT 0 CHECK (is_seed IN (0, 1)),
    is_active smallint NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at text NOT NULL,
    yt_last_discovery_at text,
    maps_last_refresh_at text
);
CREATE TABLE IF NOT EXISTS scraper.videos (
    video_id text NOT NULL,
    topic_id text NOT NULL REFERENCES scraper.topics(id) ON DELETE CASCADE,
    title text NOT NULL,
    channel_id text NOT NULL,
    channel_title text NOT NULL,
    description text NOT NULL DEFAULT '',
    published_at text NOT NULL,
    discovered_at text NOT NULL,
    discovery_source text NOT NULL,
    content_type text NOT NULL DEFAULT 'lainnya',
    is_active smallint NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    PRIMARY KEY (video_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_videos_topic
    ON scraper.videos(topic_id, is_active, published_at DESC);
CREATE TABLE IF NOT EXISTS scraper.video_stats (
    video_id text NOT NULL,
    captured_at text NOT NULL,
    views bigint NOT NULL CHECK (views >= 0),
    likes bigint,
    comments bigint,
    PRIMARY KEY (video_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_video_stats_time
    ON scraper.video_stats(captured_at);
CREATE TABLE IF NOT EXISTS scraper.places (
    place_id text NOT NULL,
    topic_id text NOT NULL REFERENCES scraper.topics(id) ON DELETE CASCADE,
    city text NOT NULL,
    is_relevant smallint NOT NULL DEFAULT 1 CHECK (is_relevant IN (0, 1)),
    is_own smallint NOT NULL DEFAULT 0 CHECK (is_own IN (0, 1)),
    first_seen_at text NOT NULL,
    last_seen_at text NOT NULL,
    PRIMARY KEY (place_id, topic_id)
);
CREATE TABLE IF NOT EXISTS scraper.place_snapshots (
    place_id text NOT NULL,
    topic_id text NOT NULL,
    captured_at text NOT NULL,
    name text NOT NULL,
    address text,
    maps_uri text,
    primary_type text,
    business_status text,
    rating double precision,
    user_rating_count bigint,
    name_mentions_product smallint NOT NULL DEFAULT 0 CHECK (name_mentions_product IN (0, 1)),
    PRIMARY KEY (place_id, topic_id, captured_at)
);
CREATE TABLE IF NOT EXISTS scraper.comments (
    id text NOT NULL,
    topic_id text REFERENCES scraper.topics(id) ON DELETE CASCADE,
    product_id text,
    source text NOT NULL,
    place_id text,
    text text NOT NULL,
    text_is_translated smallint NOT NULL DEFAULT 0 CHECK (text_is_translated IN (0, 1)),
    stars smallint CHECK (stars BETWEEN 1 AND 5),
    author_name text,
    author_uri text,
    author_hash text,
    url text,
    created_at text NOT NULL,
    collected_at text NOT NULL,
    mentions_product smallint NOT NULL DEFAULT 0 CHECK (mentions_product IN (0, 1)),
    status text NOT NULL DEFAULT 'pending',
    category text,
    sentiment text,
    score double precision CHECK (score BETWEEN -1 AND 1),
    aspects text NOT NULL DEFAULT '[]',
    topics text NOT NULL DEFAULT '[]',
    analyzer text,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    expires_at text
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_comments_topic_id
    ON scraper.comments(topic_id, id) WHERE topic_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_comments_legacy_id
    ON scraper.comments(id) WHERE topic_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_comments_feed
    ON scraper.comments(topic_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_comments_pending
    ON scraper.comments(status, collected_at);
CREATE TABLE IF NOT EXISTS scraper.summaries (
    topic_id text PRIMARY KEY REFERENCES scraper.topics(id) ON DELETE CASCADE,
    payload text NOT NULL,
    analyzer text NOT NULL,
    generated_at text NOT NULL
);
CREATE TABLE IF NOT EXISTS scraper.social_posts (
    platform text NOT NULL,
    post_id text NOT NULL,
    topic_id text NOT NULL REFERENCES scraper.topics(id) ON DELETE CASCADE,
    text text NOT NULL,
    author_name text,
    author_url text,
    url text,
    published_at text NOT NULL,
    first_seen_at text NOT NULL,
    last_seen_at text NOT NULL,
    query text,
    mentions_product smallint NOT NULL DEFAULT 0 CHECK (mentions_product IN (0, 1)),
    views bigint,
    likes bigint,
    comments bigint,
    shares bigint,
    sentiment text,
    sentiment_score double precision CHECK (sentiment_score BETWEEN -1 AND 1),
    sentiment_topics text NOT NULL DEFAULT '[]',
    sentiment_analyzer text,
    sentiment_status text NOT NULL DEFAULT 'pending',
    sentiment_attempts integer NOT NULL DEFAULT 0 CHECK (sentiment_attempts >= 0),
    PRIMARY KEY (platform, post_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_social_posts_topic
    ON scraper.social_posts(topic_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_posts_sentiment
    ON scraper.social_posts(topic_id, sentiment_status, published_at DESC);
CREATE TABLE IF NOT EXISTS scraper.social_post_stats (
    platform text NOT NULL,
    post_id text NOT NULL,
    topic_id text NOT NULL,
    captured_at text NOT NULL,
    views bigint,
    likes bigint,
    comments bigint,
    shares bigint,
    PRIMARY KEY (platform, post_id, topic_id, captured_at)
);
CREATE TABLE IF NOT EXISTS scraper.social_refreshes (
    topic_id text NOT NULL REFERENCES scraper.topics(id) ON DELETE CASCADE,
    platform text NOT NULL,
    refreshed_at text NOT NULL,
    PRIMARY KEY (topic_id, platform)
);
CREATE TABLE IF NOT EXISTS scraper.marketplace_products (
    platform text NOT NULL,
    product_id text NOT NULL,
    topic_id text NOT NULL REFERENCES scraper.topics(id) ON DELETE CASCADE,
    title text NOT NULL,
    description text NOT NULL DEFAULT '',
    url text,
    shop_name text,
    category text,
    price double precision,
    original_price double precision,
    rating double precision,
    rating_count bigint,
    sold_count bigint,
    stock bigint,
    image_url text,
    query text,
    first_seen_at text NOT NULL,
    last_seen_at text NOT NULL,
    PRIMARY KEY (platform, product_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_marketplace_products_topic
    ON scraper.marketplace_products(topic_id, platform, last_seen_at DESC);
CREATE TABLE IF NOT EXISTS scraper.marketplace_refreshes (
    topic_id text NOT NULL REFERENCES scraper.topics(id) ON DELETE CASCADE,
    platform text NOT NULL,
    refreshed_at text NOT NULL,
    PRIMARY KEY (topic_id, platform)
);
CREATE TABLE IF NOT EXISTS scraper.api_usage (
    day text NOT NULL,
    api text NOT NULL,
    units bigint NOT NULL DEFAULT 0 CHECK (units >= 0),
    PRIMARY KEY (day, api)
);

ALTER TABLE scraper.comments
    ADD COLUMN IF NOT EXISTS row_key bigint GENERATED ALWAYS AS IDENTITY;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'scraper.comments'::regclass
          AND contype = 'p'
    ) THEN
        ALTER TABLE scraper.comments
            ADD CONSTRAINT comments_pkey PRIMARY KEY (row_key);
    END IF;
END
$$;
CREATE INDEX IF NOT EXISTS idx_places_topic_id
    ON scraper.places(topic_id);

ALTER TABLE scraper.topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.videos ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.video_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.places ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.place_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.social_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.social_post_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.social_refreshes ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.marketplace_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.marketplace_refreshes ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraper.api_usage ENABLE ROW LEVEL SECURITY;
"""


def _postgres_query(sql: str) -> str:
    """Convert the qmark placeholders used by the shared helpers to asyncpg."""

    number = 0

    def replace(_: re.Match[str]) -> str:
        nonlocal number
        number += 1
        return f"${number}"

    return re.sub(r"\?", replace, sql)


def _rowcount(status: str) -> int:
    try:
        return int(status.rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0


class _Cursor:
    def __init__(self, rows: Sequence[Any] = (), *, rowcount: int = 0) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    async def fetchone(self) -> Any | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[Any]:
        return list(self._rows)


class _PoolConnection:
    """Small aiosqlite-compatible facade over an asyncpg pool."""

    def __init__(self, pool: Any) -> None:
        self.pool = pool
        self._sessions: dict[asyncio.Task[Any], tuple[Any, Any]] = {}

    def _task(self) -> asyncio.Task[Any]:
        task = asyncio.current_task()
        if task is None:  # pragma: no cover - async methods always run in a task
            raise RuntimeError("Operasi database harus berjalan di dalam asyncio task")
        return task

    async def _acquire(self) -> Any:
        try:
            return await self.pool.acquire(timeout=10)
        except TypeError:  # Lightweight test pools do not expose asyncpg's timeout argument.
            return await self.pool.acquire()

    async def _release(self, connection: Any) -> None:
        try:
            try:
                await self.pool.release(connection, timeout=10)
            except TypeError:  # Lightweight test pools do not expose asyncpg's timeout argument.
                await self.pool.release(connection)
        except asyncio.TimeoutError:
            # asyncpg terminates a connection whose reset exceeded the release
            # timeout. The completed query result must not be discarded merely
            # because Supavisor was slow while returning that connection.
            logger.warning("Supabase lambat melepas koneksi; koneksi dihentikan oleh pool")

    async def _write_session(self) -> tuple[Any, Any]:
        task = self._task()
        existing = self._sessions.get(task)
        if existing is not None:
            return existing
        connection = await self._acquire()
        transaction = connection.transaction()
        try:
            await transaction.start()
        except Exception:
            await self._release(connection)
            raise
        session = (connection, transaction)
        self._sessions[task] = session
        return session

    async def _abort(self, task: asyncio.Task[Any]) -> None:
        session = self._sessions.pop(task, None)
        if session is None:
            return
        connection, transaction = session
        try:
            await transaction.rollback()
        finally:
            await self._release(connection)

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> _Cursor:
        query = _postgres_query(sql)
        values = tuple(params)
        if query.lstrip().upper().startswith(("SELECT", "WITH")):
            session = self._sessions.get(self._task())
            if session is not None:
                rows = await session[0].fetch(query, *values)
            else:
                connection = await self._acquire()
                try:
                    rows = await connection.fetch(query, *values)
                finally:
                    await self._release(connection)
            return _Cursor(rows, rowcount=len(rows))
        task = self._task()
        connection, _ = await self._write_session()
        try:
            status = await connection.execute(query, *values)
        except Exception:
            await self._abort(task)
            raise
        return _Cursor(rowcount=_rowcount(status))

    async def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        task = self._task()
        connection, _ = await self._write_session()
        try:
            await connection.executemany(
                _postgres_query(sql), [tuple(row) for row in rows]
            )
        except Exception:
            await self._abort(task)
            raise

    async def commit(self) -> None:
        task = self._task()
        session = self._sessions.pop(task, None)
        if session is None:
            return
        connection, transaction = session
        try:
            await transaction.commit()
        finally:
            await self._release(connection)

    async def close(self) -> None:
        for task in list(self._sessions):
            await self._abort(task)


class PostgresDatabase(Database):
    """Database implementation backed by the Supabase Postgres pooler."""

    def __init__(
        self,
        dsn: str,
        *,
        comment_max_age_days: int = 180,
        auto_migrate: bool = False,
    ) -> None:
        # Do not pass the secret DSN to the SQLite base constructor or expose it
        # through ``path`` in diagnostics.
        super().__init__(":memory:", comment_max_age_days=comment_max_age_days)
        self._dsn = dsn
        self.auto_migrate = auto_migrate
        self._pool: Any | None = None
        self._adapter: _PoolConnection | None = None

    async def init(self) -> None:
        if self._pool is not None:
            return
        try:
            asyncpg = importlib.import_module("asyncpg")
        except ImportError as exc:  # pragma: no cover - deployment dependency guard
            raise RuntimeError(
                "Backend Postgres membutuhkan dependency asyncpg"
            ) from exc
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=0,
            max_size=1,
            timeout=10,
            command_timeout=30,
            max_inactive_connection_lifetime=30,
            statement_cache_size=0,
            server_settings={
                "search_path": "scraper,public",
                "application_name": "umkm-poc-scraper",
            },
        )
        if self.auto_migrate:
            try:
                await self._pool.execute(POSTGRES_SCHEMA)
            except Exception:
                await self._pool.close()
                self._pool = None
                raise
        self._adapter = _PoolConnection(self._pool)

    async def close(self) -> None:
        if self._pool is not None:
            if self._adapter is not None:
                await self._adapter.close()
            await self._pool.close()
            self._pool = None
            self._adapter = None

    def _conn(self) -> _PoolConnection:
        if self._adapter is None:
            raise RuntimeError("Database Supabase belum diinisialisasi")
        return self._adapter
