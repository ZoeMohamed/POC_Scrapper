from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db import Database
from app.social.errors import SocialBudgetExceededError
from app.social.usage import SocialUsageTracker


NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_social_caps_are_isolated_per_platform() -> None:
    database = Database(":memory:")
    await database.init()
    tracker = SocialUsageTracker(
        database,
        daily_cap=3,
        monthly_cap=30,
        platform_daily_cap=1,
        platform_monthly_cap=10,
    )

    await tracker.consume("tiktok", now=NOW)
    with pytest.raises(SocialBudgetExceededError):
        await tracker.consume("tiktok", now=NOW)
    await tracker.consume("facebook", now=NOW)

    status = await tracker.status(now=NOW)
    assert status["today"] == 2
    assert status["by_platform_today"] == {
        "tiktok": 1,
        "instagram": 0,
        "facebook": 1,
    }
    assert status["by_platform_remaining"]["instagram"] == 1
    await database.close()


@pytest.mark.asyncio
async def test_legacy_social_cap_remains_shared_when_platform_caps_are_omitted() -> None:
    database = Database(":memory:")
    await database.init()
    tracker = SocialUsageTracker(database, daily_cap=1, monthly_cap=10)

    await tracker.consume("tiktok", now=NOW)
    with pytest.raises(SocialBudgetExceededError):
        await tracker.consume("facebook", now=NOW)
    await database.close()
