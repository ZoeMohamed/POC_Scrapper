"""Async SQLite persistence for v3 topics, trends, opinions, and API usage."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import aiosqlite

from app.collectors.filters import is_comment_within_age
from app.models import (
    AnalyzerName, Comment, CommentIn, SentimentResult, Topic, TopicCreate,
    Video, VideoStat,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'umum',
    keywords TEXT NOT NULL,
    product_terms TEXT NOT NULL DEFAULT '[]',
    exclude_terms TEXT NOT NULL DEFAULT '[]',
    cities TEXT NOT NULL,
    own_place_id TEXT,
    status TEXT NOT NULL DEFAULT 'discovering',
    is_seed INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    yt_last_discovery_at TEXT,
    maps_last_refresh_at TEXT
);
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    title TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    discovery_source TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'lainnya',
    is_active INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (video_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_videos_topic ON videos(topic_id, is_active, published_at DESC);
CREATE TABLE IF NOT EXISTS video_stats (
    video_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    views INTEGER NOT NULL,
    likes INTEGER,
    comments INTEGER,
    PRIMARY KEY (video_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_video_stats_time ON video_stats(captured_at);
CREATE TABLE IF NOT EXISTS places (
    place_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    city TEXT NOT NULL,
    is_relevant INTEGER NOT NULL DEFAULT 1,
    is_own INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (place_id, topic_id)
);
CREATE TABLE IF NOT EXISTS place_snapshots (
    place_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    name TEXT NOT NULL,
    address TEXT,
    maps_uri TEXT,
    primary_type TEXT,
    business_status TEXT,
    rating REAL,
    user_rating_count INTEGER,
    name_mentions_product INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (place_id, topic_id, captured_at)
);
CREATE TABLE IF NOT EXISTS comments (
    id TEXT NOT NULL,
    topic_id TEXT,
    product_id TEXT,
    source TEXT NOT NULL,
    place_id TEXT,
    text TEXT NOT NULL,
    text_is_translated INTEGER NOT NULL DEFAULT 0,
    stars INTEGER,
    author_name TEXT,
    author_uri TEXT,
    author_hash TEXT,
    url TEXT,
    created_at TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    mentions_product INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    category TEXT,
    sentiment TEXT,
    score REAL,
    aspects TEXT NOT NULL DEFAULT '[]',
    topics TEXT NOT NULL DEFAULT '[]',
    analyzer TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    PRIMARY KEY (id, topic_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_comments_legacy_id ON comments(id) WHERE topic_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_comments_feed ON comments(topic_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_comments_pending ON comments(status, collected_at);
CREATE TABLE IF NOT EXISTS summaries (
    topic_id TEXT PRIMARY KEY REFERENCES topics(id),
    payload TEXT NOT NULL,
    analyzer TEXT NOT NULL,
    generated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS social_posts (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    text TEXT NOT NULL,
    author_name TEXT,
    author_url TEXT,
    url TEXT,
    published_at TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    query TEXT,
    mentions_product INTEGER NOT NULL DEFAULT 0,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    sentiment TEXT,
    sentiment_score REAL,
    sentiment_topics TEXT NOT NULL DEFAULT '[]',
    sentiment_analyzer TEXT,
    sentiment_status TEXT NOT NULL DEFAULT 'pending',
    sentiment_attempts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, post_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_social_posts_topic ON social_posts(topic_id, published_at DESC);
CREATE TABLE IF NOT EXISTS social_post_stats (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    PRIMARY KEY (platform, post_id, topic_id, captured_at)
);
CREATE TABLE IF NOT EXISTS social_refreshes (
    topic_id TEXT NOT NULL REFERENCES topics(id),
    platform TEXT NOT NULL,
    refreshed_at TEXT NOT NULL,
    PRIMARY KEY (topic_id, platform)
);
CREATE TABLE IF NOT EXISTS marketplace_products (
    platform TEXT NOT NULL,
    product_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES topics(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    url TEXT,
    shop_name TEXT,
    category TEXT,
    price REAL,
    original_price REAL,
    rating REAL,
    rating_count INTEGER,
    sold_count INTEGER,
    stock INTEGER,
    image_url TEXT,
    query TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (platform, product_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_marketplace_products_topic
    ON marketplace_products(topic_id, platform, last_seen_at DESC);
CREATE TABLE IF NOT EXISTS marketplace_refreshes (
    topic_id TEXT NOT NULL REFERENCES topics(id),
    platform TEXT NOT NULL,
    refreshed_at TEXT NOT NULL,
    PRIMARY KEY (topic_id, platform)
);
CREATE TABLE IF NOT EXISTS api_usage (
    day TEXT NOT NULL,
    api TEXT NOT NULL,
    units INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, api)
);
"""


def to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def from_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized or "topik"


def _loads(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _row_to_topic(row: aiosqlite.Row) -> Topic:
    data = dict(row)
    for key in ("keywords", "product_terms", "exclude_terms", "cities"):
        data[key] = _loads(data.get(key))
    data["is_seed"] = bool(data["is_seed"])
    data["is_active"] = bool(data["is_active"])
    return Topic.model_validate(data)


def _row_to_video(row: aiosqlite.Row) -> Video:
    data = dict(row)
    data["is_active"] = bool(data["is_active"])
    return Video.model_validate(data)


def _row_to_comment(row: aiosqlite.Row) -> Comment:
    data = dict(row)
    data["product_id"] = data.get("product_id") or data.get("topic_id") or "unknown"
    data["topics"] = _loads(data.get("topics") or data.get("aspects"))
    allowed = Comment.model_fields
    return Comment.model_validate({key: value for key, value in data.items() if key in allowed})


class Database:
    """Lifecycle-owned SQLite connection with explicit domain helpers."""

    def __init__(self, path: str | Path, *, comment_max_age_days: int = 180) -> None:
        self.path = str(path)
        self.comment_max_age_days = comment_max_age_days
        self._connection: aiosqlite.Connection | None = None

    async def init(self) -> None:
        if self._connection is not None:
            return
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA journal_mode=WAL")
        await connection.execute("PRAGMA busy_timeout=5000")
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.executescript(SCHEMA)
        await self._migrate_social_sentiment(connection)
        await connection.commit()
        self._connection = connection

    @staticmethod
    async def _migrate_social_sentiment(connection: aiosqlite.Connection) -> None:
        """Add social sentiment fields to databases created before the social analyzer."""
        cursor = await connection.execute("PRAGMA table_info(social_posts)")
        columns = {str(row[1]) for row in await cursor.fetchall()}
        migrations = (
            ("sentiment", "TEXT"),
            ("sentiment_score", "REAL"),
            ("sentiment_topics", "TEXT NOT NULL DEFAULT '[]'"),
            ("sentiment_analyzer", "TEXT"),
            ("sentiment_status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("sentiment_attempts", "INTEGER NOT NULL DEFAULT 0"),
        )
        for name, definition in migrations:
            if name not in columns:
                await connection.execute(
                    f"ALTER TABLE social_posts ADD COLUMN {name} {definition}"
                )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_social_posts_sentiment "
            "ON social_posts(topic_id, sentiment_status, published_at DESC)"
        )

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    def _conn(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database belum diinisialisasi")
        return self._connection

    async def seed_topics(self, path: str | Path) -> int:
        cursor = await self._conn().execute("SELECT COUNT(*) FROM topics")
        if int((await cursor.fetchone())[0]) > 0:
            return 0
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        inserted = 0
        for raw in payload:
            topic = TopicCreate.model_validate({
                key: value for key, value in raw.items() if key != "own_place_id"
            })
            await self.create_topic(topic, is_seed=True, own_place_id=raw.get("own_place_id"))
            inserted += 1
        return inserted

    async def create_topic(
        self, data: TopicCreate, *, is_seed: bool = False,
        own_place_id: str | None = None,
    ) -> Topic:
        base = slugify(data.name)
        candidate = base
        suffix = 2
        while await self.get_topic(candidate, include_inactive=True):
            candidate = f"{base}-{suffix}"
            suffix += 1
        now = to_utc_iso(datetime.now(timezone.utc))
        await self._conn().execute(
            """INSERT INTO topics
               (id,name,category,keywords,product_terms,exclude_terms,cities,
                own_place_id,status,is_seed,is_active,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                candidate, data.name, data.category, json.dumps(data.keywords),
                json.dumps(data.product_terms), json.dumps(data.exclude_terms),
                json.dumps(data.cities), own_place_id, "discovering",
                int(is_seed), 1, now,
            ),
        )
        await self._conn().commit()
        topic = await self.get_topic(candidate)
        assert topic is not None
        return topic

    async def get_topic(self, topic_id: str, *, include_inactive: bool = False) -> Topic | None:
        clause = "" if include_inactive else "AND is_active=1"
        cursor = await self._conn().execute(
            f"SELECT * FROM topics WHERE id=? {clause}", (topic_id,)
        )
        row = await cursor.fetchone()
        return _row_to_topic(row) if row else None

    async def list_topics(self, *, active_only: bool = True) -> list[Topic]:
        where = "WHERE is_active=1" if active_only else ""
        cursor = await self._conn().execute(
            f"SELECT * FROM topics {where} ORDER BY is_seed DESC, created_at ASC"
        )
        return [_row_to_topic(row) for row in await cursor.fetchall()]

    async def count_active_topics(self) -> int:
        cursor = await self._conn().execute("SELECT COUNT(*) FROM topics WHERE is_active=1")
        return int((await cursor.fetchone())[0])

    async def update_topic_status(
        self, topic_id: str, status: str, *, discovery_at: datetime | None = None
    ) -> None:
        if discovery_at:
            await self._conn().execute(
                "UPDATE topics SET status=?, yt_last_discovery_at=? WHERE id=?",
                (status, to_utc_iso(discovery_at), topic_id),
            )
        else:
            await self._conn().execute(
                "UPDATE topics SET status=? WHERE id=?", (status, topic_id)
            )
        await self._conn().commit()

    async def update_topic_maps_refresh(
        self, topic_id: str, refreshed_at: datetime, *, status: str | None = None
    ) -> None:
        if status:
            await self._conn().execute(
                "UPDATE topics SET status=?, maps_last_refresh_at=? WHERE id=?",
                (status, to_utc_iso(refreshed_at), topic_id),
            )
        else:
            await self._conn().execute(
                "UPDATE topics SET maps_last_refresh_at=? WHERE id=?",
                (to_utc_iso(refreshed_at), topic_id),
            )
        await self._conn().commit()

    async def upsert_place(
        self, *, topic_id: str, place_id: str, city: str, is_relevant: bool,
        is_own: bool = False, seen_at: datetime,
    ) -> None:
        timestamp = to_utc_iso(seen_at)
        await self._conn().execute(
            """INSERT INTO places
               (place_id,topic_id,city,is_relevant,is_own,first_seen_at,last_seen_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(place_id,topic_id) DO UPDATE SET
                city=excluded.city,is_relevant=excluded.is_relevant,
                is_own=CASE WHEN places.is_own > excluded.is_own
                    THEN places.is_own ELSE excluded.is_own END,
                last_seen_at=excluded.last_seen_at""",
            (place_id, topic_id, city, int(is_relevant), int(is_own), timestamp, timestamp),
        )
        await self._conn().commit()

    async def insert_place_snapshot(
        self, *, topic_id: str, place_id: str, captured_at: datetime,
        name: str, address: str | None, maps_uri: str | None,
        primary_type: str | None, business_status: str | None,
        rating: float | None, user_rating_count: int | None,
        name_mentions_product: bool,
    ) -> None:
        await self._conn().execute(
            """INSERT INTO place_snapshots
               (place_id,topic_id,captured_at,name,address,maps_uri,primary_type,
                business_status,rating,user_rating_count,name_mentions_product)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(place_id,topic_id,captured_at) DO UPDATE SET
                name=excluded.name,address=excluded.address,maps_uri=excluded.maps_uri,
                primary_type=excluded.primary_type,business_status=excluded.business_status,
                rating=excluded.rating,user_rating_count=excluded.user_rating_count,
                name_mentions_product=excluded.name_mentions_product""",
            (
                place_id, topic_id, to_utc_iso(captured_at), name, address, maps_uri,
                primary_type, business_status, rating, user_rating_count,
                int(name_mentions_product),
            ),
        )
        await self._conn().commit()

    async def insert_maps_comment(
        self, *, topic_id: str, place_id: str, review_id: str, text: str,
        stars: int | None, author_name: str | None, author_uri: str | None,
        url: str | None, created_at: datetime, collected_at: datetime,
        mentions_product: bool, category: str, expires_at: datetime,
        max_comment_chars: int = 800,
    ) -> bool:
        cursor = await self._conn().execute(
            """INSERT INTO comments
               (id,topic_id,product_id,source,place_id,text,stars,author_name,
                author_uri,url,created_at,collected_at,mentions_product,category,
                expires_at,status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending')
               ON CONFLICT DO NOTHING""",
            (
                f"gm_{review_id}", topic_id, topic_id, "gmaps", place_id,
                text[:max_comment_chars], stars, author_name, author_uri, url,
                to_utc_iso(created_at), to_utc_iso(collected_at), int(mentions_product),
                category, to_utc_iso(expires_at),
            ),
        )
        await self._conn().commit()
        return cursor.rowcount == 1

    async def count_relevant_places(self, topic_id: str) -> int:
        cursor = await self._conn().execute(
            "SELECT COUNT(*) FROM places WHERE topic_id=? AND is_relevant=1", (topic_id,)
        )
        return int((await cursor.fetchone())[0])

    async def list_places_latest(self, topic_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn().execute(
            """SELECT p.place_id,p.topic_id,p.city,p.is_relevant,p.is_own,
                      p.first_seen_at,p.last_seen_at,s.captured_at,s.name,s.address,
                      s.maps_uri,s.primary_type,s.business_status,s.rating,
                      s.user_rating_count,s.name_mentions_product
               FROM places p
               LEFT JOIN place_snapshots s ON s.place_id=p.place_id AND s.topic_id=p.topic_id
                 AND s.captured_at=(SELECT MAX(s2.captured_at) FROM place_snapshots s2
                                    WHERE s2.place_id=p.place_id AND s2.topic_id=p.topic_id)
               WHERE p.topic_id=? ORDER BY p.is_relevant DESC,p.last_seen_at DESC,p.place_id""",
            (topic_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_topic_feed(
        self, topic_id: str, *, limit: int = 50, before: tuple[datetime, str] | None = None
    ) -> list[Comment]:
        clauses, params = [
            "topic_id=?",
            "source='gmaps'",
            "mentions_product=1",
            "category='opini_produk'",
        ], [topic_id]
        if before:
            cursor_time = to_utc_iso(before[0])
            clauses.append("(created_at<? OR (created_at=? AND id<?))")
            params.extend((cursor_time, cursor_time, before[1]))
        params.append(min(max(limit, 1), 200))
        cursor = await self._conn().execute(
            f"SELECT * FROM comments WHERE {' AND '.join(clauses)} ORDER BY created_at DESC,id DESC LIMIT ?",
            params,
        )
        return [_row_to_comment(row) for row in await cursor.fetchall()]

    async def purge_expired_maps(self, *, now: datetime, snapshot_ttl_days: int = 7) -> int:
        """Remove cached Maps content after its explicit POC TTL."""
        cutoff = to_utc_iso(now)
        cursor = await self._conn().execute(
            "DELETE FROM comments WHERE source='gmaps' AND expires_at IS NOT NULL AND expires_at<?",
            (cutoff,),
        )
        deleted = cursor.rowcount
        snapshot_cutoff = to_utc_iso(
            now.replace(microsecond=0) - timedelta(days=snapshot_ttl_days)
        )
        await self._conn().execute(
            "DELETE FROM place_snapshots WHERE captured_at<?", (snapshot_cutoff,)
        )
        await self._conn().commit()
        return deleted

    async def upsert_social_post(
        self, *, platform: str, post_id: str, topic_id: str, text: str,
        author_name: str | None, author_url: str | None, url: str | None,
        published_at: datetime, seen_at: datetime, query: str | None,
        mentions_product: bool, views: int | None, likes: int | None,
        comments: int | None, shares: int | None,
    ) -> bool:
        timestamp = to_utc_iso(seen_at)
        existing = await self._conn().execute(
            "SELECT 1 FROM social_posts WHERE platform=? AND post_id=? AND topic_id=?",
            (platform, post_id, topic_id),
        )
        is_new = await existing.fetchone() is None
        cursor = await self._conn().execute(
            """INSERT INTO social_posts
               (platform,post_id,topic_id,text,author_name,author_url,url,published_at,
                first_seen_at,last_seen_at,query,mentions_product,views,likes,comments,shares)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(platform,post_id,topic_id) DO UPDATE SET
                text=excluded.text,author_name=excluded.author_name,author_url=excluded.author_url,
                url=excluded.url,last_seen_at=excluded.last_seen_at,query=excluded.query,
                mentions_product=excluded.mentions_product,views=excluded.views,likes=excluded.likes,
                comments=excluded.comments,shares=excluded.shares""",
            (
                platform, post_id, topic_id, text, author_name, author_url, url,
                to_utc_iso(published_at), timestamp, timestamp, query,
                int(mentions_product), views, likes, comments, shares,
            ),
        )
        await self._conn().execute(
            """INSERT INTO social_post_stats
               (platform,post_id,topic_id,captured_at,views,likes,comments,shares)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(platform,post_id,topic_id,captured_at) DO UPDATE SET
                views=excluded.views,likes=excluded.likes,
                comments=excluded.comments,shares=excluded.shares""",
            (platform, post_id, topic_id, timestamp, views, likes, comments, shares),
        )
        await self._conn().commit()
        return is_new and cursor.rowcount == 1

    async def update_social_refresh(self, topic_id: str, platform: str, refreshed_at: datetime) -> None:
        await self._conn().execute(
            """INSERT INTO social_refreshes(topic_id,platform,refreshed_at) VALUES (?,?,?)
               ON CONFLICT(topic_id,platform) DO UPDATE SET refreshed_at=excluded.refreshed_at""",
            (topic_id, platform, to_utc_iso(refreshed_at)),
        )
        await self._conn().commit()

    async def get_social_last_refresh(self, topic_id: str, platform: str) -> datetime | None:
        cursor = await self._conn().execute(
            "SELECT refreshed_at FROM social_refreshes WHERE topic_id=? AND platform=?",
            (topic_id, platform),
        )
        row = await cursor.fetchone()
        return from_iso(row[0]) if row else None

    async def upsert_marketplace_product(
        self, *, platform: str, product_id: str, topic_id: str, title: str,
        description: str, url: str | None, shop_name: str | None,
        category: str | None, price: float | None, original_price: float | None,
        rating: float | None, rating_count: int | None, sold_count: int | None,
        stock: int | None, image_url: str | None, query: str | None,
        seen_at: datetime,
    ) -> bool:
        timestamp = to_utc_iso(seen_at)
        existing = await self._conn().execute(
            "SELECT 1 FROM marketplace_products WHERE platform=? AND product_id=? AND topic_id=?",
            (platform, product_id, topic_id),
        )
        is_new = await existing.fetchone() is None
        cursor = await self._conn().execute(
            """INSERT INTO marketplace_products
               (platform,product_id,topic_id,title,description,url,shop_name,category,
                price,original_price,rating,rating_count,sold_count,stock,image_url,query,
                first_seen_at,last_seen_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(platform,product_id,topic_id) DO UPDATE SET
                title=excluded.title,description=excluded.description,url=excluded.url,
                shop_name=excluded.shop_name,category=excluded.category,price=excluded.price,
                original_price=excluded.original_price,rating=excluded.rating,
                rating_count=excluded.rating_count,sold_count=excluded.sold_count,
                stock=excluded.stock,image_url=excluded.image_url,query=excluded.query,
                last_seen_at=excluded.last_seen_at""",
            (platform, product_id, topic_id, title, description, url, shop_name, category,
             price, original_price, rating, rating_count, sold_count, stock, image_url,
             query, timestamp, timestamp),
        )
        await self._conn().commit()
        return is_new and cursor.rowcount == 1

    async def update_marketplace_refresh(self, topic_id: str, platform: str, refreshed_at: datetime) -> None:
        await self._conn().execute(
            """INSERT INTO marketplace_refreshes(topic_id,platform,refreshed_at) VALUES (?,?,?)
               ON CONFLICT(topic_id,platform) DO UPDATE SET refreshed_at=excluded.refreshed_at""",
            (topic_id, platform, to_utc_iso(refreshed_at)),
        )
        await self._conn().commit()

    async def get_marketplace_last_refresh(self, topic_id: str, platform: str) -> datetime | None:
        cursor = await self._conn().execute(
            "SELECT refreshed_at FROM marketplace_refreshes WHERE topic_id=? AND platform=?",
            (topic_id, platform),
        )
        row = await cursor.fetchone()
        return from_iso(row[0]) if row else None

    async def list_marketplace_products(self, topic_id: str, *, platform: str = "shopee", limit: int = 100) -> list[dict[str, Any]]:
        cursor = await self._conn().execute(
            """SELECT * FROM marketplace_products WHERE topic_id=? AND platform=?
               ORDER BY COALESCE(sold_count,0) DESC, COALESCE(rating,0) DESC, last_seen_at DESC LIMIT ?""",
            (topic_id, platform, min(max(limit, 1), 500)),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def marketplace_stats(self, topic_id: str, *, platform: str = "shopee") -> dict[str, Any]:
        cursor = await self._conn().execute(
            """SELECT COUNT(*) AS products, COALESCE(SUM(sold_count),0) AS sold_count,
                      AVG(rating) AS average_rating, COALESCE(SUM(rating_count),0) AS rating_count,
                      MIN(price) AS min_price, MAX(price) AS max_price
               FROM marketplace_products WHERE topic_id=? AND platform=?""",
            (topic_id, platform),
        )
        row = await cursor.fetchone()
        data = dict(row) if row else {}
        return {
            "platform": platform, "products": int(data.get("products") or 0),
            "sold_count": int(data.get("sold_count") or 0),
            "average_rating": round(float(data["average_rating"]), 2) if data.get("average_rating") is not None else None,
            "rating_count": int(data.get("rating_count") or 0),
            "min_price": float(data["min_price"]) if data.get("min_price") is not None else None,
            "max_price": float(data["max_price"]) if data.get("max_price") is not None else None,
        }

    async def list_pending_social_posts(
        self, topic_id: str | None = None, *, limit: int = 25
    ) -> list[dict[str, Any]]:
        clauses = ["mentions_product=1", "COALESCE(sentiment_status, 'pending')='pending'"]
        params: list[Any] = []
        if topic_id:
            clauses.append("topic_id=?")
            params.append(topic_id)
        params.append(min(max(limit, 1), 200))
        cursor = await self._conn().execute(
            f"""SELECT * FROM social_posts WHERE {' AND '.join(clauses)}
                ORDER BY published_at ASC, post_id ASC LIMIT ?""",
            params,
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def update_social_sentiment(
        self, *, platform: str, post_id: str, topic_id: str,
        sentiment: str, score: float, topics: list[str], analyzer: str,
    ) -> None:
        await self._conn().execute(
            """UPDATE social_posts
               SET sentiment=?, sentiment_score=?, sentiment_topics=?,
                   sentiment_analyzer=?, sentiment_status='analyzed',
                   sentiment_attempts=sentiment_attempts+1
               WHERE platform=? AND post_id=? AND topic_id=?""",
            (
                sentiment, max(-1.0, min(1.0, float(score))), json.dumps(topics),
                analyzer, platform, post_id, topic_id,
            ),
        )
        await self._conn().commit()

    async def mark_social_sentiment_attempt(
        self, *, platform: str, post_id: str, topic_id: str, failed: bool = False
    ) -> None:
        await self._conn().execute(
            """UPDATE social_posts
               SET sentiment_attempts=sentiment_attempts+1,
                   sentiment_status=CASE WHEN ? AND sentiment_attempts+1 >= 3
                       THEN 'failed' ELSE COALESCE(sentiment_status, 'pending') END
               WHERE platform=? AND post_id=? AND topic_id=?""",
            (int(failed), platform, post_id, topic_id),
        )
        await self._conn().commit()

    async def list_social_posts(
        self, topic_id: str, *, platform: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        clauses, params = ["topic_id=?", "mentions_product=1"], [topic_id]
        if platform:
            clauses.append("platform=?")
            params.append(platform)
        params.append(min(max(limit, 1), 500))
        cursor = await self._conn().execute(
            f"""SELECT * FROM social_posts WHERE {' AND '.join(clauses)}
                ORDER BY published_at DESC,post_id DESC LIMIT ?""",
            params,
        )
        rows = []
        for row in await cursor.fetchall():
            item = dict(row)
            item["sentiment_topics"] = _loads(item.get("sentiment_topics"))
            rows.append(item)
        return rows

    async def social_stats(self, topic_id: str) -> dict[str, Any]:
        cursor = await self._conn().execute(
            """SELECT platform,post_id,published_at,views,likes,comments,shares,
                      sentiment,sentiment_score,sentiment_topics
               FROM social_posts WHERE topic_id=? AND mentions_product=1
               ORDER BY published_at ASC,post_id ASC""",
            (topic_id,),
        )
        platform_data: dict[str, dict[str, Any]] = {}
        sentiment = {"positif": 0, "negatif": 0, "netral": 0, "pending": 0}
        daily: dict[str, dict[str, int | str]] = {}
        topic_data: dict[str, dict[str, int | str]] = {}
        score_total = 0.0
        score_count = 0
        for raw in await cursor.fetchall():
            row = dict(raw)
            platform = str(row["platform"])
            item = platform_data.setdefault(platform, {
                "platform": platform, "posts": 0, "views": 0, "likes": 0,
                "comments": 0, "shares": 0,
                "sentiment": {"positif": 0, "negatif": 0, "netral": 0, "pending": 0},
            })
            item["posts"] += 1
            for metric in ("views", "likes", "comments", "shares"):
                item[metric] += int(row[metric] or 0)
            label = str(row["sentiment"] or "pending")
            if label not in sentiment:
                label = "pending"
            sentiment[label] += 1
            item["sentiment"][label] += 1
            score = row["sentiment_score"]
            if score is not None:
                score_total += float(score)
                score_count += 1
            day = str(row["published_at"] or "")[:10] or "unknown"
            point = daily.setdefault(day, {"date": day, "positif": 0, "negatif": 0, "netral": 0, "pending": 0})
            point[label] += 1
            for topic in _loads(row.get("sentiment_topics")):
                topic_item = topic_data.setdefault(topic, {"topic": topic, "total": 0, "positif": 0, "negatif": 0, "netral": 0})
                topic_item["total"] += 1
                if label in ("positif", "negatif", "netral"):
                    topic_item[label] += 1
        analyzed = sentiment["positif"] + sentiment["negatif"] + sentiment["netral"]
        dominant = max(("positif", "negatif", "netral"), key=lambda key: sentiment[key]) if analyzed else "pending"
        positive_rate = sentiment["positif"] / analyzed if analyzed else 0.0
        negative_rate = sentiment["negatif"] / analyzed if analyzed else 0.0
        daily_values = sorted(daily.values(), key=lambda row: str(row["date"]))[-30:]
        return {
            "platforms": list(platform_data.values()),
            "total_posts": sum(int(row["posts"]) for row in platform_data.values()),
            "sentiment": sentiment,
            "analyzed_posts": analyzed,
            "pending_posts": sentiment["pending"],
            "positive_rate": round(positive_rate, 4),
            "negative_rate": round(negative_rate, 4),
            "net_score": round(score_total / score_count, 4) if score_count else None,
            "dominant_sentiment": dominant,
            "top_topics": sorted(topic_data.values(), key=lambda row: int(row["total"]), reverse=True)[:8],
            "daily": daily_values,
        }

    async def deactivate_topic(self, topic_id: str) -> bool:
        cursor = await self._conn().execute(
            "UPDATE topics SET is_active=0,status='inactive' WHERE id=? AND is_active=1",
            (topic_id,),
        )
        await self._conn().commit()
        return cursor.rowcount == 1

    async def upsert_videos(self, videos: Sequence[Video]) -> int:
        inserted = 0
        for video in videos:
            cursor = await self._conn().execute(
                """INSERT INTO videos
                   (video_id,topic_id,title,channel_id,channel_title,description,
                    published_at,discovered_at,discovery_source,content_type,is_active)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(video_id,topic_id) DO UPDATE SET
                    title=excluded.title,channel_title=excluded.channel_title,
                    description=excluded.description,content_type=excluded.content_type,
                    is_active=1""",
                (
                    video.video_id, video.topic_id, video.title, video.channel_id,
                    video.channel_title, video.description, to_utc_iso(video.published_at),
                    to_utc_iso(video.discovered_at), video.discovery_source,
                    video.content_type, int(video.is_active),
                ),
            )
            inserted += int(cursor.rowcount > 0)
        await self._conn().commit()
        return inserted

    async def list_videos(
        self, topic_id: str, *, active_only: bool = True,
        content_type: str | None = None,
    ) -> list[Video]:
        clauses, params = ["topic_id=?"], [topic_id]
        if active_only:
            clauses.append("is_active=1")
        if content_type:
            clauses.append("content_type=?")
            params.append(content_type)
        cursor = await self._conn().execute(
            f"SELECT * FROM videos WHERE {' AND '.join(clauses)} ORDER BY published_at DESC",
            params,
        )
        return [_row_to_video(row) for row in await cursor.fetchall()]

    async def deactivate_old_videos(self, topic_id: str, cutoff: datetime) -> int:
        cursor = await self._conn().execute(
            "UPDATE videos SET is_active=0 WHERE topic_id=? AND published_at<? AND is_active=1",
            (topic_id, to_utc_iso(cutoff)),
        )
        await self._conn().commit()
        return cursor.rowcount

    async def deactivate_videos(self, topic_id: str, video_ids: Sequence[str]) -> int:
        """Deactivate a bounded set of videos rejected by a newer filter."""

        ids = list(dict.fromkeys(str(video_id) for video_id in video_ids if video_id))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        cursor = await self._conn().execute(
            f"UPDATE videos SET is_active=0 WHERE topic_id=? AND video_id IN ({placeholders}) AND is_active=1",
            [topic_id, *ids],
        )
        await self._conn().commit()
        return cursor.rowcount

    async def insert_video_stats(self, stats: Sequence[VideoStat]) -> int:
        if not stats:
            return 0
        await self._conn().executemany(
            """INSERT INTO video_stats
               (video_id,captured_at,views,likes,comments) VALUES (?,?,?,?,?)
               ON CONFLICT(video_id,captured_at) DO UPDATE SET
                views=excluded.views,likes=excluded.likes,comments=excluded.comments""",
            [
                (item.video_id, to_utc_iso(item.captured_at), item.views, item.likes, item.comments)
                for item in stats
            ],
        )
        await self._conn().commit()
        return len(stats)

    async def get_video_stats_rows(self, topic_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn().execute(
            """SELECT s.* FROM video_stats s JOIN videos v ON v.video_id=s.video_id
               WHERE v.topic_id=? ORDER BY s.captured_at ASC""", (topic_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_last_snapshot_at(self, topic_id: str) -> datetime | None:
        cursor = await self._conn().execute(
            """SELECT MAX(s.captured_at) FROM video_stats s
               JOIN videos v ON v.video_id=s.video_id WHERE v.topic_id=?""", (topic_id,),
        )
        return from_iso((await cursor.fetchone())[0])

    async def usage_get(self, day: str, api: str) -> int:
        cursor = await self._conn().execute(
            "SELECT units FROM api_usage WHERE day=? AND api=?", (day, api)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def usage_add(self, day: str, api: str, units: int) -> int:
        await self._conn().execute(
            """INSERT INTO api_usage(day,api,units) VALUES (?,?,?)
               ON CONFLICT(day,api) DO UPDATE
               SET units=api_usage.units+excluded.units""",
            (day, api, units),
        )
        await self._conn().commit()
        return await self.usage_get(day, api)

    async def usage_rows(self, prefix: str | None = None) -> list[dict[str, Any]]:
        if prefix:
            cursor = await self._conn().execute(
                "SELECT * FROM api_usage WHERE api LIKE ? ORDER BY day DESC,api",
                (f"{prefix}%",),
            )
        else:
            cursor = await self._conn().execute("SELECT * FROM api_usage ORDER BY day DESC,api")
        return [dict(row) for row in await cursor.fetchall()]

    async def usage_summary(self, prefix: str, day: str) -> list[dict[str, Any]]:
        """Return daily/monthly totals per API using one bounded query."""

        cursor = await self._conn().execute(
            """SELECT api,
                      COALESCE(SUM(CASE WHEN day=? THEN units ELSE 0 END),0) AS today_units,
                      COALESCE(SUM(CASE WHEN day LIKE ? THEN units ELSE 0 END),0) AS month_units
               FROM api_usage
               WHERE api LIKE ?
               GROUP BY api
               ORDER BY api""",
            (day, f"{day[:7]}%", f"{prefix}%"),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Compatibility helpers for v2 analyzer and bridge tests. ---
    async def insert_comment(self, item: CommentIn, *, max_comment_chars: int = 800) -> bool:
        now_dt = datetime.now(timezone.utc)
        if not is_comment_within_age(item.created_at, self.comment_max_age_days, now=now_dt):
            return False
        cursor = await self._conn().execute(
            """INSERT INTO comments
               (id,topic_id,product_id,source,text,url,author_hash,created_at,collected_at)
               VALUES (?,NULL,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
            (
                item.id, item.product_id, item.source, item.text[:max_comment_chars],
                item.url, item.author_hash, to_utc_iso(item.created_at), to_utc_iso(now_dt),
            ),
        )
        await self._conn().commit()
        return cursor.rowcount == 1

    async def insert_comments(
        self, items: Iterable[CommentIn], *, max_comment_chars: int = 800
    ) -> list[Comment]:
        inserted: list[Comment] = []
        for item in items:
            if await self.insert_comment(item, max_comment_chars=max_comment_chars):
                found = await self.get_comment(item.id)
                if found:
                    inserted.append(found)
        return inserted

    async def get_comment(self, comment_id: str) -> Comment | None:
        cursor = await self._conn().execute("SELECT * FROM comments WHERE id=?", (comment_id,))
        row = await cursor.fetchone()
        return _row_to_comment(row) if row else None

    async def get_feed(
        self, *, product_id: str | None = None, sentiment: str | None = None,
        source: str | None = None, q: str | None = None, limit: int = 50,
        since: datetime | None = None, before: tuple[datetime, str] | None = None,
    ) -> list[Comment]:
        clauses, params = ["topic_id IS NULL"], []
        if product_id:
            clauses.append("product_id=?"); params.append(product_id)
        if sentiment == "pending":
            clauses.append("status='pending'")
        elif sentiment:
            clauses.append("sentiment=?"); params.append(sentiment)
        if source:
            clauses.append("source=?"); params.append(source)
        if q:
            clauses.append("text LIKE ? ESCAPE '\\'")
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        if since:
            clauses.append("created_at>=?"); params.append(to_utc_iso(since))
        if before:
            cursor_time = to_utc_iso(before[0])
            clauses.append("(created_at<? OR (created_at=? AND id<?))")
            params.extend((cursor_time, cursor_time, before[1]))
        params.append(min(max(limit, 1), 200))
        cursor = await self._conn().execute(
            f"SELECT * FROM comments WHERE {' AND '.join(clauses)} ORDER BY created_at DESC,id DESC LIMIT ?",
            params,
        )
        return [_row_to_comment(row) for row in await cursor.fetchall()]

    async def fetch_pending(self, limit: int = 25, max_attempts: int = 5) -> list[Comment]:
        cursor = await self._conn().execute(
            """SELECT * FROM comments WHERE (topic_id IS NULL OR source='gmaps') AND status='pending'
               AND attempts<? ORDER BY collected_at ASC LIMIT ?""", (max_attempts, limit),
        )
        return [_row_to_comment(row) for row in await cursor.fetchall()]

    async def get_pending_comments(self, limit: int = 25, max_attempts: int = 5) -> list[Comment]:
        return await self.fetch_pending(limit, max_attempts)

    async def update_analysis(self, result: SentimentResult, analyzer: AnalyzerName) -> Comment | None:
        await self._conn().execute(
            """UPDATE comments SET status='analyzed',sentiment=?,score=?,topics=?,aspects=?,
               analyzer=?,attempts=attempts+1 WHERE id=?""",
            (result.sentiment, result.score, json.dumps(result.topics),
             json.dumps(result.topics), analyzer, result.id),
        )
        await self._conn().commit()
        return await self.get_comment(result.id)

    async def update_comment_analysis(
        self, *, comment_id: str, sentiment: str, score: float,
        topics: list[str], analyzer: str,
    ) -> Comment | None:
        return await self.update_analysis(
            SentimentResult(id=comment_id, sentiment=sentiment, score=score, topics=topics),  # type: ignore[arg-type]
            analyzer,  # type: ignore[arg-type]
        )

    async def increment_attempts(self, ids: Iterable[str], *, fail_at: int = 5) -> None:
        values = list(ids)
        if not values:
            return
        placeholders = ",".join("?" for _ in values)
        await self._conn().execute(
            f"""UPDATE comments SET attempts=attempts+1,
                status=CASE WHEN attempts+1>=? THEN 'failed' ELSE status END
                WHERE id IN ({placeholders})""", [fail_at, *values],
        )
        await self._conn().commit()

    async def count_pending(self) -> int:
        cursor = await self._conn().execute(
            "SELECT COUNT(*) FROM comments WHERE (topic_id IS NULL OR source='gmaps') AND status='pending'"
        )
        return int((await cursor.fetchone())[0])

    async def get_analyzed_recent(self, product_id: str | None = None, limit: int = 60) -> list[Comment]:
        clause, params = ("AND product_id=?", [product_id]) if product_id else ("", [])
        cursor = await self._conn().execute(
            f"SELECT * FROM comments WHERE topic_id IS NULL AND status='analyzed' {clause} ORDER BY collected_at DESC LIMIT ?",
            [*params, limit],
        )
        return [_row_to_comment(row) for row in await cursor.fetchall()]

    async def get_stats_rows(self, product_id: str | None = None, since: datetime | None = None) -> list[Comment]:
        clauses, params = ["topic_id IS NULL"], []
        if product_id:
            clauses.append("product_id=?"); params.append(product_id)
        if since:
            clauses.append("created_at>=?"); params.append(to_utc_iso(since))
        cursor = await self._conn().execute(
            f"SELECT * FROM comments WHERE {' AND '.join(clauses)}", params
        )
        return [_row_to_comment(row) for row in await cursor.fetchall()]
