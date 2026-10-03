#!/usr/bin/env python3
"""Jalankan satu collector sekali untuk debug."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.collectors.base import BaseCollector  # noqa: E402
from app.collectors.inbox import InboxCollector  # noqa: E402
from app.collectors.playstore import PlayStoreCollector  # noqa: E402
from app.collectors.replay import ReplayCollector  # noqa: E402
from app.collectors.youtube import YouTubeCollector  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.models import Product  # noqa: E402
from app.products import load_products  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ambil data dari satu sumber sekali")
    parser.add_argument("source", choices=("replay", "youtube", "playstore", "inbox"))
    parser.add_argument("--product", help="Batasi ke satu product_id")
    parser.add_argument("--save", action="store_true", help="Simpan hasil ke SQLite")
    return parser.parse_args()


def make_collector(source: str, settings: Settings) -> BaseCollector:
    if source == "replay":
        return ReplayCollector(settings.seed_comments_path, settings.replay_interval_seconds)
    if source == "youtube":
        return YouTubeCollector(
            settings.youtube_api_key,
            settings.collect_interval_seconds,
            settings.youtube_videos_per_product,
            settings.youtube_search_refresh_minutes,
        )
    if source == "playstore":
        return PlayStoreCollector(settings.collect_interval_seconds)
    return InboxCollector(settings.inbox_path, settings.collect_interval_seconds)


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    products = load_products(settings.products_path)
    if args.product:
        products = [product for product in products if product.id == args.product]
        if not products:
            print(f"Product tidak dikenal: {args.product}", file=sys.stderr)
            return 2
    try:
        collector = make_collector(args.source, settings)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        comments = await collector.collect(products)
        for comment in comments:
            print(comment.model_dump_json())
        if args.save:
            database = Database(
                settings.database_path,
                comment_max_age_days=settings.comment_max_age_days,
            )
            await database.init()
            try:
                inserted = await database.insert_comments(
                    comments, max_comment_chars=settings.max_comment_chars
                )
            finally:
                await database.close()
            print(f"Tersimpan {len(inserted)} dari {len(comments)} komentar.")
        else:
            print(f"Ditemukan {len(comments)} komentar (tidak disimpan).")
    finally:
        await collector.close()
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
