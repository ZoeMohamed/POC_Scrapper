from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.db import Database
from app.marketplace.apify_client import ShopeeApifyClient
from app.marketplace.parsing import parse_shopee_items
from app.marketplace.usage import MarketplaceUsageTracker
from app.models import Topic
from app.models import TopicCreate


def _topic() -> Topic:
    return Topic(id="sepatu-lokal", name="Sepatu Lokal", category="fashion", keywords=["sepatu lokal"], product_terms=["sepatu", "sneakers"], cities=["Bandung"], created_at="2026-01-01T00:00:00Z")


def test_shopee_parser_filters_irrelevant_and_normalizes_metrics() -> None:
    rows = parse_shopee_items([
        {"itemId": "1", "title": "Sepatu Lokal Sneakers Bandung", "price": "Rp 125.000", "rating": 4.8, "sold": "120", "shopName": "Toko UMKM"},
        {"itemId": "2", "title": "Kabel USB", "price": 10000},
    ], _topic(), query="sepatu lokal")
    assert len(rows) == 1
    assert rows[0].price == 125000
    assert rows[0].sold_count == 120
    assert rows[0].mentions_product is True


@pytest.mark.asyncio
async def test_shopee_actor_run_poll_and_budget(tmp_path: Path) -> None:
    statuses = iter([
        {"data": {"id": "run-shopee", "defaultDatasetId": "ds-shopee", "status": "RUNNING"}},
        {"data": {"id": "run-shopee", "defaultDatasetId": "ds-shopee", "status": "SUCCEEDED"}},
    ])
    calls: list[tuple[str, str, dict | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, str(request.url), body))
        assert request.headers["authorization"] == "Bearer test-token"
        if request.method == "POST" and "/acts/xtracto~shopee-scraper/runs" in str(request.url):
            return httpx.Response(201, json=next(statuses))
        if request.method == "GET" and "/actor-runs/run-shopee" in str(request.url):
            return httpx.Response(200, json=next(statuses))
        if request.method == "GET" and "/datasets/ds-shopee/items" in str(request.url):
            return httpx.Response(200, json=[{"itemId": "1", "title": "Sepatu Lokal", "price": 100000}])
        return httpx.Response(404)

    db = Database(tmp_path / "marketplace.db")
    await db.init()
    settings = Settings(_env_file=None, apify_token="test-token", apify_poll_interval_seconds=0.001, apify_poll_timeout_seconds=2, database_path=tmp_path / "marketplace.db", marketplace_results_per_query=30)
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = ShopeeApifyClient(settings, MarketplaceUsageTracker(db, daily_cap=2, monthly_cap=2), client=http_client)
    result = await client.collect(_topic())
    start = next(call for call in calls if call[0] == "POST" and "/runs" in call[1])
    assert start[2]["country"] == "id"
    assert start[2]["mode"] == "keyword"
    assert start[2]["maxProducts"] == 30
    assert result.items[0]["itemId"] == "1"
    assert sum(row["units"] for row in await db.usage_rows("marketplace_")) == 1
    await http_client.aclose()
    await db.close()


@pytest.mark.asyncio
async def test_marketplace_products_persist_and_aggregate(tmp_path: Path) -> None:
    db = Database(tmp_path / "marketplace-store.db")
    await db.init()
    topic = await db.create_topic(TopicCreate(name="Sepatu Lokal", keywords=["sepatu lokal"], product_terms=["sepatu"], cities=["Bandung"], category="fashion"))
    now = topic.created_at
    inserted = await db.upsert_marketplace_product(
        platform="shopee", product_id="shoe-1", topic_id=topic.id, title="Sepatu Lokal",
        description="", url="https://shopee.co.id/x", shop_name="Toko", category="Fashion",
        price=125000, original_price=150000, rating=4.8, rating_count=20, sold_count=100,
        stock=5, image_url=None, query="sepatu lokal", seen_at=now,
    )
    assert inserted is True
    assert (await db.marketplace_stats(topic.id))["sold_count"] == 100
    assert len(await db.list_marketplace_products(topic.id)) == 1
    await db.close()
