"""Persistent YouTube quota accounting using Pacific calendar days."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.db import Database

from .errors import YouTubeQuotaExceededError

PACIFIC = ZoneInfo("America/Los_Angeles")
BUCKETS = ("yt_search", "yt_read", "yt_demo")


class QuotaTracker:
    def __init__(
        self, database: Database, *, daily_quota: int = 10_000,
        search_reserve: int = 6_000, demo_budget: int = 1_500,
    ) -> None:
        self.database = database
        self.daily_quota = daily_quota
        self.search_reserve = search_reserve
        self.demo_budget = demo_budget

    @staticmethod
    def day(now: datetime | None = None) -> str:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(PACIFIC).date().isoformat()

    async def consume(self, api: str, units: int, *, now: datetime | None = None) -> int:
        if api not in BUCKETS or units < 1:
            raise ValueError("Kantong atau unit YouTube tidak valid")
        day = self.day(now)
        usage = {bucket: await self.database.usage_get(day, bucket) for bucket in BUCKETS}
        total = sum(usage.values())
        if total + units > self.daily_quota:
            raise YouTubeQuotaExceededError("Kuota YouTube harian habis")
        if api == "yt_search" and usage[api] + units > self.search_reserve:
            raise YouTubeQuotaExceededError("Jatah pencarian YouTube harian habis")
        if api == "yt_demo" and usage[api] + units > self.demo_budget:
            raise YouTubeQuotaExceededError("Anggaran mode demo YouTube habis")
        return await self.database.usage_add(day, api, units)

    async def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        day = self.day(now)
        usage = {bucket: await self.database.usage_get(day, bucket) for bucket in BUCKETS}
        total = sum(usage.values())
        ratio = total / self.daily_quota
        level = "habis" if total >= self.daily_quota else "kritis" if ratio >= 0.8 else "hemat"
        return {
            "day": day,
            "buckets": usage,
            "used": total,
            "limit": self.daily_quota,
            "remaining": max(0, self.daily_quota - total),
            "level": level,
            "reset_timezone": "America/Los_Angeles",
        }
