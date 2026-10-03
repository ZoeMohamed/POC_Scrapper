#!/usr/bin/env python3
"""Pastikan database demo berisi sedikitnya 30 komentar replay teranalisis."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.analyzer.mock import MockAnalyzer  # noqa: E402
from app.collectors.replay import ReplayCollector  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.products import load_products  # noqa: E402

TARGET_COMMENTS = 30


async def warmup() -> None:
    settings = Settings()
    products = load_products(settings.products_path)
    database = Database(
        settings.database_path,
        comment_max_age_days=settings.comment_max_age_days,
    )
    replay = ReplayCollector(settings.seed_comments_path, random_seed=2026)
    analyzer = MockAnalyzer()
    await database.init()
    try:
        existing = await database.get_feed(limit=200)
        needed = max(0, TARGET_COMMENTS - len(existing))
        candidates = []
        for _ in range(needed):
            candidates.extend(await replay.collect(products))
        inserted = await database.insert_comments(
            candidates, max_comment_chars=settings.max_comment_chars
        )
        results = await analyzer.analyze(
            [(comment.id, comment.text) for comment in inserted]
        )
        for result in results:
            await database.update_analysis(result, "mock")
        total = len(existing) + len(inserted)
    finally:
        await database.close()
    print(f"Warmup selesai: {total} komentar tersedia ({len(inserted)} baru).")


if __name__ == "__main__":
    asyncio.run(warmup())
