"""Persistent request caps for Google Maps Platform calls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db import Database

from .errors import MapsBudgetExceededError


class MapsUsageTracker:
    def __init__(
        self, database: Database, *, daily_cap: int = 30, monthly_cap: int = 800
    ) -> None:
        self.database = database
        self.daily_cap = daily_cap
        self.monthly_cap = monthly_cap

    @staticmethod
    def day(now: datetime | None = None) -> str:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date().isoformat()

    async def consume(self, api: str, units: int = 1, *, now: datetime | None = None) -> int:
        if not api.startswith("maps_") or units < 1:
            raise ValueError("Nama API atau unit Maps tidak valid")
        day = self.day(now)
        rows = await self.database.usage_rows("maps_")
        daily = sum(int(row["units"]) for row in rows if row["day"] == day)
        monthly = sum(int(row["units"]) for row in rows if str(row["day"]).startswith(day[:7]))
        if daily + units > self.daily_cap:
            raise MapsBudgetExceededError("Batas request Google Maps hari ini tercapai")
        if monthly + units > self.monthly_cap:
            raise MapsBudgetExceededError("Batas request Google Maps bulan ini tercapai")
        return await self.database.usage_add(day, api, units)

    async def refund(self, api: str, units: int = 1, *, now: datetime | None = None) -> None:
        if not api.startswith("maps_") or units < 1:
            return
        day = self.day(now)
        if await self.database.usage_get(day, api) >= units:
            await self.database.usage_add(day, api, -units)

    async def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        day = self.day(now)
        rows = await self.database.usage_rows("maps_")
        daily = sum(int(row["units"]) for row in rows if row["day"] == day)
        monthly = sum(int(row["units"]) for row in rows if str(row["day"]).startswith(day[:7]))
        return {
            "day": day,
            "month": day[:7],
            "today": daily,
            "daily_limit": self.daily_cap,
            "this_month": monthly,
            "monthly_limit": self.monthly_cap,
            "level": "habis" if daily >= self.daily_cap or monthly >= self.monthly_cap else "hemat",
        }
