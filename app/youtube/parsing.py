"""Normalization helpers for YouTube API and public-page payloads."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


def text_value(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("simpleText"):
            return str(value["simpleText"])
        return "".join(str(item.get("text", "")) for item in value.get("runs", []))
    return str(value or "")


def parse_count(value: Any) -> int:
    text = text_value(value).lower().replace(".", "").replace(",", ".")
    match = re.search(r"([\d.]+)\s*(rb|ribu|k|jt|juta|m|miliar)?", text)
    if not match:
        return 0
    try:
        number = float(match.group(1))
    except ValueError:
        return 0
    scale = {
        "rb": 1_000, "ribu": 1_000, "k": 1_000,
        "jt": 1_000_000, "juta": 1_000_000, "m": 1_000_000,
        "miliar": 1_000_000_000,
    }.get(match.group(2), 1)
    return int(number * scale)


def relative_datetime(value: Any, *, now: datetime | None = None) -> datetime:
    reference = now or datetime.now(timezone.utc)
    text = text_value(value).casefold()
    match = re.search(
        r"(\d+)\s+(detik|dtk|second|seconds|menit|mnt|minute|minutes|jam|hour|hours|"
        r"hari|day|days|minggu|mgg|week|weeks|bulan|bln|month|months|tahun|thn|year|years)",
        text,
    )
    if not match:
        return reference
    amount = int(match.group(1))
    seconds = {
        "detik": 1, "dtk": 1, "second": 1, "seconds": 1,
        "menit": 60, "mnt": 60, "minute": 60, "minutes": 60,
        "jam": 3600, "hour": 3600, "hours": 3600,
        "hari": 86400, "day": 86400, "days": 86400,
        "minggu": 604800, "mgg": 604800, "week": 604800, "weeks": 604800,
        "bulan": 2592000, "bln": 2592000, "month": 2592000, "months": 2592000,
        "tahun": 31536000, "thn": 31536000, "year": 31536000, "years": 31536000,
    }[match.group(2)]
    return reference - timedelta(seconds=amount * seconds)


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)
