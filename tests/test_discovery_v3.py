from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.db import Database
from app.models import TopicCreate
from app.youtube.content_type import ContentTypeClassifier
from app.youtube.trend_discovery import TrendDiscovery, build_query, is_relevant


class FakeTrendClient:
    mode = "api"

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.searches: list[tuple[str, str]] = []

    async def search_videos(self, query: str, order: str, published_after: datetime, max_results: int = 50, page_token: str | None = None) -> tuple[list[str], str | None]:
        del published_after, max_results
        self.searches.append((query, order))
        if order == "date" and page_token is None:
            return ["good", "noise", "old", "upcoming"], "page-2"
        if order == "date":
            return ["good-2", "good"], None
        return ["good", "good-2"], None

    async def get_videos(self, ids: list[str], parts: str = "snippet,statistics", usage_bucket: str = "yt_read") -> list[dict[str, Any]]:
        del parts, usage_bucket
        data = {
            "good": self.item("good", "Review jujur keripik pisang", 2, 1200),
            "good-2": self.item("good-2", "Ide usaha jualan keripik pisang", 8, 3000),
            "noise": self.item("noise", "Pertandingan sepak bola", 1, 50),
            "old": self.item("old", "Keripik pisang zaman dulu", 100, 9000),
            "upcoming": {**self.item("upcoming", "Keripik pisang besok", 1, 0), "live_broadcast_content": "upcoming"},
        }
        return [data[item] for item in ids]

    def item(self, video_id: str, title: str, age: int, views: int) -> dict[str, Any]:
        return {"video_id": video_id, "title": title, "description": "produk UMKM", "channel_id": "channel", "channel_title": "Kreator", "published_at": self.now - timedelta(days=age), "live_broadcast_content": "none", "views": views, "likes": 4, "comments": 2}


@pytest.mark.asyncio
async def test_discovery_keeps_only_current_product_video(tmp_path: Path) -> None:
    now = datetime(2026, 9, 30, 5, tzinfo=timezone.utc)
    database = Database(tmp_path / "trend.db")
    await database.init()
    topic = await database.create_topic(TopicCreate(name="Keripik Pisang", keywords=["keripik pisang"], product_terms=["keripik", "pisang"], exclude_terms=["sepatu"], cities=["Bandung"]))
    client = FakeTrendClient(now)
    settings = Settings(database_path=tmp_path / "trend.db", yt_search_date_pages=2, yt_trend_lookback_days=90)
    discovery = TrendDiscovery(database, client, settings, ContentTypeClassifier("rules"))

    result = await discovery.discover(topic, now=now)

    assert build_query(topic) == '"keripik pisang" -sepatu'
    assert result.found == 5
    assert {video.video_id for video in result.videos} == {"good", "good-2"}
    assert {video.content_type for video in result.videos} == {"review", "ide_usaha"}
    assert [order for _, order in client.searches] == ["date", "date", "viewCount"]
    assert '-"upin ipin"' in client.searches[0][0]
    assert len(await database.get_video_stats_rows(topic.id)) == 2
    await database.close()


def test_relevance_checks_product_and_exclusions() -> None:
    now = datetime.now(timezone.utc)
    topic_data = TopicCreate(name="Parfum Lokal", keywords=["parfum lokal"], product_terms=["parfum"], exclude_terms=["mobil"], cities=["Bandung"])
    from app.models import Topic
    topic = Topic(id="parfum-lokal", **topic_data.model_dump(), created_at=now)
    assert is_relevant({"title": "Review parfum lokal tahan lama", "description": ""}, topic)
    assert not is_relevant({"title": "Parfum mobil lokal", "description": ""}, topic)
    assert not is_relevant({"title": "Wisata Bandung", "description": ""}, topic)


def test_relevance_rejects_youtube_entertainment_for_food_topic() -> None:
    now = datetime.now(timezone.utc)
    from app.models import Topic
    topic = Topic(
        id="ayam-goreng", name="Ayam Goreng", keywords=["ayam goreng"],
        product_terms=["ayam", "goreng"], exclude_terms=[], cities=["Bandung"],
        category="makanan_minuman", created_at=now,
    )

    assert not is_relevant({
        "title": "Upin & Ipin Musim 20 - Ayam Goreng Mail Mendunia (Full Episode)",
        "description": "Tonton kisah terbaru kami.",
        "channel_title": "Upin & Ipin Animation",
    }, topic)
    assert not is_relevant({
        "title": "Ayam Goreng Mail Mendunia",
        "description": "Cerita anak hari ini.",
        "channel_title": "Sahabat Selamanya Upin & Ipin TV",
    }, topic)
    assert not is_relevant({
        "title": "Ayam Goreng Terbang",
        "description": "Kompilasi lucu tanpa konteks produk.",
        "channel_title": "Kanal Hiburan",
    }, topic)
    assert is_relevant({
        "title": "Ayam goreng keju chili meletup buatan UMKM Bandung",
        "description": "Menu jualan rumahan dan harga terbaru.",
        "channel_title": "Kuliner Lokal",
    }, topic)


def test_build_query_can_add_global_youtube_exclusions() -> None:
    now = datetime.now(timezone.utc)
    from app.models import Topic
    topic = Topic(
        id="ayam-goreng", name="Ayam Goreng", keywords=["ayam goreng"],
        product_terms=["ayam", "goreng"], exclude_terms=["film"],
        cities=["Bandung"], created_at=now,
    )

    query = build_query(topic, extra_excludes=["upin ipin", "episode"])
    assert query == '"ayam goreng" -film -"upin ipin" -episode'
