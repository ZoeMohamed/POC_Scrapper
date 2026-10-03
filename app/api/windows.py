"""Shared time-window definitions for feed and statistics endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

Window = Literal["1h", "24h", "7d", "30d", "90d", "all"]

WINDOW_DELTA: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


def since_for_window(window: Window, *, now: datetime | None = None) -> datetime | None:
    """Return the inclusive UTC lower bound for a named dashboard window."""
    if window == "all":
        return None
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return reference.astimezone(timezone.utc) - WINDOW_DELTA[window]
