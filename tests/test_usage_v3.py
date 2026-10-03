from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.db import Database
from app.maps.errors import MapsBudgetExceededError
from app.maps.usage import MapsUsageTracker
from app.youtube.errors import YouTubeQuotaExceededError
from app.youtube.quota import QuotaTracker


@pytest.mark.asyncio
async def test_youtube_quota_buckets_and_search_reserve(tmp_path: Path) -> None:
    database = Database(tmp_path / "usage.db"); await database.init()
    tracker = QuotaTracker(database, daily_quota=500, search_reserve=200, demo_budget=50)
    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    assert await tracker.consume("yt_search", 100, now=now) == 100
    assert await tracker.consume("yt_read", 1, now=now) == 1
    with pytest.raises(YouTubeQuotaExceededError):
        await tracker.consume("yt_search", 101, now=now)
    status = await tracker.status(now=now)
    assert status["used"] == 101
    assert status["reset_timezone"] == "America/Los_Angeles"
    await database.close()


@pytest.mark.asyncio
async def test_maps_daily_cap_is_enforced(tmp_path: Path) -> None:
    database = Database(tmp_path / "maps.db"); await database.init()
    tracker = MapsUsageTracker(database, daily_cap=2, monthly_cap=10)
    await tracker.consume("maps_search")
    await tracker.consume("maps_details")
    with pytest.raises(MapsBudgetExceededError):
        await tracker.consume("maps_details")
    assert (await tracker.status())["today"] == 2
    await database.close()
