from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.db import Database
from app.events import EventBroker
from app.models import Topic, TopicCreate
from app.analyzer.worker import AnalyzerWorker
from app.social.apify_client import SocialApifyClient
from app.social.parsing import parse_social_items
from app.social.sentiment import SocialSentimentService
from app.social.usage import SocialUsageTracker


def topic() -> Topic:
    return Topic(
        id="sepatu-lokal", name="Sepatu Lokal", category="fashion",
        keywords=["sepatu lokal", "sneakers lokal"],
        product_terms=["sepatu", "sneakers"], cities=["Bandung"],
        created_at="2026-01-01T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_tiktok_actor_batches_queries_without_comments_or_media(tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict | None]] = []
    statuses = iter([
        {"data": {"id": "run-tt", "defaultDatasetId": "ds-tt", "status": "RUNNING"}},
        {"data": {"id": "run-tt", "defaultDatasetId": "ds-tt", "status": "SUCCEEDED"}},
    ])

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, str(request.url), body))
        assert request.headers["authorization"] == "Bearer test-token"
        if request.method == "POST" and "/actors/clockworks~tiktok-scraper/runs" in str(request.url):
            return httpx.Response(201, json=next(statuses))
        if request.method == "GET" and "/actor-runs/run-tt" in str(request.url):
            return httpx.Response(200, json=next(statuses))
        if request.method == "GET" and "/datasets/ds-tt/items" in str(request.url):
            return httpx.Response(200, json=[{"id": "v1", "text": "Sepatu lokal nyaman", "createTimeISO": "2026-09-30T00:00:00Z"}])
        return httpx.Response(404)

    db = Database(tmp_path / "social.db")
    await db.init()
    usage = SocialUsageTracker(db, daily_cap=5, monthly_cap=5)
    settings = Settings(
        _env_file=None, apify_token="test-token", apify_poll_interval_seconds=0.001,
        apify_poll_timeout_seconds=2, database_path=tmp_path / "social.db",
        social_max_queries_per_topic=3, social_results_per_query=50,
    )
    transport = httpx.MockTransport(handler)
    client_http = httpx.AsyncClient(transport=transport)
    client = SocialApifyClient(settings, usage, client=client_http)
    result = await client.collect("tiktok", topic())
    start = next(call for call in calls if call[0] == "POST" and "/runs" in call[1])
    assert start[2]["resultsPerPage"] == 50
    assert len(start[2]["searchQueries"]) == 3
    assert start[2]["commentsPerPost"] == 0
    assert start[2]["shouldDownloadVideos"] is False
    assert result.items[0]["id"] == "v1"
    assert sum(row["units"] for row in await db.usage_rows("social_")) == 1
    await client_http.aclose()
    await db.close()


def test_instagram_input_and_social_parser() -> None:
    settings = Settings(_env_file=None, apify_token="x", social_results_per_query=30)
    client = SocialApifyClient(settings, SocialUsageTracker(Database(":memory:")))
    payload = client.build_input("instagram", topic())
    assert payload["resultsType"] == "posts"
    assert len(payload["directUrls"]) == 3
    assert payload["resultsLimit"] == 30
    posts = parse_social_items("instagram", [{
        "id": "ig-1", "shortCode": "ABC", "caption": "Sepatu lokal Bandung",
        "timestamp": "2026-09-30T00:00:00Z", "likesCount": 23,
        "commentsCount": 4, "ownerUsername": "toko_sepatu",
    }], topic())
    assert posts[0].url == "https://www.instagram.com/p/ABC/"
    assert posts[0].mentions_product is True
    assert posts[0].likes == 23


def test_facebook_keyword_input_and_parser() -> None:
    settings = Settings(_env_file=None, apify_token="x", social_results_per_query=50, facebook_results_per_query=25)
    client = SocialApifyClient(settings, SocialUsageTracker(Database(":memory:")))
    payload = client.build_input("facebook", topic())
    assert payload["categories"] == ["sepatu lokal", "sneakers lokal", "sepatu"]
    assert payload["searchType"] == "posts"
    assert payload["resultsLimit"] == 25
    posts = parse_social_items("facebook", [{
        "postId": "fb-1", "postText": "Sepatu lokal nyaman untuk harian",
        "publishedAt": "2026-09-30T00:00:00Z", "authorName": "UMKM Bandung",
        "likes": 12, "comments": 3, "shares": 2, "url": "https://facebook.com/p/1",
    }], topic())
    assert posts[0].mentions_product is True
    assert posts[0].shares == 2


def test_facebook_parser_supports_actor_user_and_page_objects() -> None:
    posts = parse_social_items("facebook", [{
        "postId": "28484036627928046",
        "text": "Sepatu lokal Bandung nyaman",
        "url": "https://www.facebook.com/example/posts/1",
        "user": {"id": "100002452675154", "name": "Warung Bandung"},
        "pageName": {"id": "100002452675154", "name": "Warung Bandung"},
        "likes": 11, "comments": 15, "shares": 1,
        "time": "2026-10-01T05:50:54.000Z",
    }], topic())
    assert len(posts) == 1
    assert posts[0].post_id == "28484036627928046"
    assert posts[0].author_name == "Warung Bandung"
    assert posts[0].author_url == "https://www.facebook.com/100002452675154"
    assert posts[0].mentions_product is True


@pytest.mark.asyncio
async def test_social_sentiment_is_persisted_and_aggregated(tmp_path: Path) -> None:
    db = Database(tmp_path / "social-sentiment.db")
    await db.init()
    topic_row = await db.create_topic(TopicCreate(
        name="Sepatu Lokal", keywords=["sepatu lokal"],
        product_terms=["sepatu"], exclude_terms=[], category="fashion", cities=["Bandung"],
    ))
    now = topic_row.created_at
    for platform, post_id, text in (
        ("tiktok", "tt-positive", "Sepatu lokal bagus dan nyaman"),
        ("instagram", "ig-negative", "Sepatu ini mahal dan mengecewakan"),
    ):
        await db.upsert_social_post(
            platform=platform, post_id=post_id, topic_id=topic_row.id,
            text=text, author_name="akun", author_url=None, url=None,
            published_at=now, seen_at=now, query="sepatu lokal", mentions_product=True,
            views=10, likes=2, comments=1, shares=0,
        )
    settings = Settings(_env_file=None, ai_mode="lexicon", database_path=tmp_path / "social-sentiment.db")
    worker = AnalyzerWorker(settings, db, EventBroker())
    service = SocialSentimentService(db, worker, EventBroker(), batch_size=10)
    result = await service.analyze_topic(topic_row.id)
    assert result["analyzed"] == 2
    stats = await db.social_stats(topic_row.id)
    assert stats["sentiment"] == {"positif": 1, "negatif": 1, "netral": 0, "pending": 0}
    assert stats["dominant_sentiment"] in {"positif", "negatif"}
    posts = await db.list_social_posts(topic_row.id)
    assert {post["sentiment"] for post in posts} == {"positif", "negatif"}
    await db.close()
