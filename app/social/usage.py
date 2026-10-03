"""Persistent Actor-run caps isolated per social platform."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db import Database

from .errors import SocialBudgetExceededError


class SocialUsageTracker:
    def __init__(
        self,
        database: Database,
        *,
        daily_cap: int = 30,
        monthly_cap: int = 600,
        platform_daily_cap: int | None = None,
        platform_monthly_cap: int | None = None,
    ) -> None:
        self.database = database
        self.daily_cap = daily_cap
        self.monthly_cap = monthly_cap
        self.platform_daily_cap = platform_daily_cap
        self.platform_monthly_cap = platform_monthly_cap

    @staticmethod
    def day(now: datetime | None = None) -> str:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date().isoformat()

    async def consume(self, platform: str, *, now: datetime | None = None) -> int:
        if platform not in {"tiktok", "instagram", "facebook"}:
            raise ValueError("Platform sosial tidak valid")
        day = self.day(now)
        rows = await self.database.usage_summary("social_", day)
        api = f"social_{platform}_run"
        row = next((item for item in rows if item["api"] == api), None)
        platform_daily = int(row["today_units"]) if row else 0
        platform_monthly = int(row["month_units"]) if row else 0
        daily = sum(int(item["today_units"]) for item in rows)
        monthly = sum(int(item["month_units"]) for item in rows)
        daily_limit = self.platform_daily_cap or self.daily_cap
        monthly_limit = self.platform_monthly_cap or self.monthly_cap
        daily_used = platform_daily if self.platform_daily_cap is not None else daily
        monthly_used = platform_monthly if self.platform_monthly_cap is not None else monthly
        if daily_used >= daily_limit:
            raise SocialBudgetExceededError("Batas run sosial hari ini tercapai")
        if monthly_used >= monthly_limit:
            raise SocialBudgetExceededError("Batas run sosial bulan ini tercapai")
        return await self.database.usage_add(day, api, 1)

    async def refund(self, platform: str, *, now: datetime | None = None) -> None:
        """Release a reservation when Apify rejected the run before start."""
        if platform not in {"tiktok", "instagram", "facebook"}:
            return
        day = self.day(now)
        api = f"social_{platform}_run"
        if await self.database.usage_get(day, api) > 0:
            await self.database.usage_add(day, api, -1)

    async def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        day = self.day(now)
        rows = await self.database.usage_summary("social_", day)
        by_platform = {
            platform: next(
                (
                    int(row["today_units"])
                    for row in rows
                    if row["api"] == f"social_{platform}_run"
                ),
                0,
            )
            for platform in ("tiktok", "instagram", "facebook")
        }
        by_platform_month = {
            platform: next(
                (
                    int(row["month_units"])
                    for row in rows
                    if row["api"] == f"social_{platform}_run"
                ),
                0,
            )
            for platform in ("tiktok", "instagram", "facebook")
        }
        daily = sum(by_platform.values())
        monthly = sum(by_platform_month.values())
        platform_daily_limit = self.platform_daily_cap or self.daily_cap
        platform_monthly_limit = self.platform_monthly_cap or self.monthly_cap
        exhausted = any(
            by_platform[platform] >= platform_daily_limit
            or by_platform_month[platform] >= platform_monthly_limit
            for platform in by_platform
        )
        return {
            "day": day,
            "month": day[:7],
            "today": daily,
            "by_platform_today": by_platform,
            "daily_limit": self.daily_cap,
            "this_month": monthly,
            "monthly_limit": self.monthly_cap,
            "platform_daily_limit": platform_daily_limit,
            "platform_monthly_limit": platform_monthly_limit,
            "by_platform_remaining": {
                platform: max(0, platform_daily_limit - used)
                for platform, used in by_platform.items()
            },
            "level": "sebagian_habis" if exhausted else "hemat",
        }
