#!/usr/bin/env python3
"""Probe a product trend from YouTube without modifying the application database."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.analyzer.rate_limiter import AsyncRateLimiter
from app.config import Settings
from app.db import Database
from app.models import TopicCreate
from app.youtube.client import PublicYouTubeClient, YouTubeClient
from app.youtube.content_type import ContentTypeClassifier, GeminiTitleClassifier
from app.youtube.quota import QuotaTracker
from app.youtube.trend_discovery import TrendDiscovery


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Uji discovery tren produk YouTube")
    parser.add_argument("product", help='Nama produk, contoh: "cappuccino cincau"')
    parser.add_argument("--city", default="Bandung", help="Disimpan sebagai konteks topik")
    return parser.parse_args()


async def run(product: str, city: str) -> None:
    settings = Settings()
    tokens = [token for token in product.casefold().split() if len(token) >= 3]
    with tempfile.TemporaryDirectory(prefix="umkm-yt-probe-") as directory:
        database = Database(Path(directory) / "probe.db")
        await database.init()
        tracker = QuotaTracker(
            database, daily_quota=settings.youtube_daily_quota,
            search_reserve=settings.yt_search_reserve_units,
            demo_budget=settings.demo_budget_units,
        )
        client = (
            YouTubeClient(settings.youtube_api_key, tracker, timeout=settings.youtube_http_timeout_seconds)
            if settings.youtube_api_key
            else PublicYouTubeClient(timeout=settings.youtube_http_timeout_seconds)
        )
        gemini = None
        if settings.video_classifier == "auto" and settings.gemini_api_key:
            try:
                gemini = GeminiTitleClassifier(settings, AsyncRateLimiter(settings.gemini_rpm))
            except (ImportError, RuntimeError, ValueError):
                pass
        classifier = ContentTypeClassifier(settings.video_classifier, gemini=gemini)
        topic = await database.create_topic(TopicCreate(
            name=product.title(), keywords=[product.casefold()],
            product_terms=list(dict.fromkeys([product.casefold(), *tokens]))[:8],
            cities=[city],
        ))
        try:
            result = await TrendDiscovery(database, client, settings, classifier).discover(topic)
            counts = Counter(video.content_type for video in result.videos)
            stats = await database.get_video_stats_rows(topic.id)
            views = {str(row["video_id"]): int(row["views"]) for row in stats}
            print(f"Mode sumber : {client.mode}")
            print(f"Query       : {result.query}")
            print(f"Kandidat    : {result.found}")
            print(f"Relevan     : {result.relevant}")
            print("Komposisi   : " + ", ".join(f"{kind}={counts.get(kind, 0)}" for kind in ("review", "resep", "ide_usaha", "lainnya")))
            print("\nVideo teratas:")
            ranked = sorted(result.videos, key=lambda item: views.get(item.video_id, 0), reverse=True)
            for index, video in enumerate(ranked[:10], start=1):
                print(f"{index:>2}. [{video.content_type}] {video.title} — {views.get(video.video_id, 0):,} views")
            usage = await tracker.status()
            print(f"\nUnit YouTube API terpakai: {usage['used']}" if client.mode == "api" else "\nUnit YouTube API terpakai: 0 (mode halaman publik)")
        finally:
            await client.close()
            await database.close()


if __name__ == "__main__":
    args = arguments()
    asyncio.run(run(args.product, args.city))
