"""Persistent Apify run caps for marketplace sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db import Database

from .errors import MarketplaceBudgetExceededError


class MarketplaceUsageTracker:
    def __init__(self, database: Database, *, daily_cap: int = 8, monthly_cap: int = 200) -> None:
        self.database = database
        self.daily_cap = daily_cap
        self.monthly_cap = monthly_cap

    @staticmethod
    def day(now: datetime | None = None) -> str:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date().isoformat()

    async def consume(self, platform: str, *, now: datetime | None = None) -> int:
        if platform != "shopee":
            raise ValueError("Platform marketplace tidak valid")
        day = self.day(now)
        rows = await self.database.usage_summary("marketplace_", day)
        daily = sum(int(row["today_units"]) for row in rows)
        monthly = sum(int(row["month_units"]) for row in rows)
        if daily >= self.daily_cap:
            raise MarketplaceBudgetExceededError("Batas run marketplace hari ini tercapai")
        if monthly >= self.monthly_cap:
            raise MarketplaceBudgetExceededError("Batas run marketplace bulan ini tercapai")
        return await self.database.usage_add(day, f"marketplace_{platform}_run", 1)

    async def refund(self, platform: str, *, now: datetime | None = None) -> None:
        if platform != "shopee":
            return
        day = self.day(now)
        api = f"marketplace_{platform}_run"
        if await self.database.usage_get(day, api) > 0:
            await self.database.usage_add(day, api, -1)

    async def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        day = self.day(now)
        rows = await self.database.usage_summary("marketplace_", day)
        by_platform = {
            "shopee": next(
                (int(row["today_units"]) for row in rows if row["api"] == "marketplace_shopee_run"),
                0,
            )
        }
        daily = sum(int(row["today_units"]) for row in rows)
        monthly = sum(int(row["month_units"]) for row in rows)
        return {
            "day": day, "month": day[:7], "today": daily, "by_platform_today": by_platform,
            "daily_limit": self.daily_cap, "this_month": monthly, "monthly_limit": self.monthly_cap,
            "level": "habis" if daily >= self.daily_cap or monthly >= self.monthly_cap else "hemat",
        }
