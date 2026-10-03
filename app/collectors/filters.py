"""Source-independent collector filters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def is_comment_within_age(
    published_at: datetime,
    max_age_days: int,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether a comment is no older than the configured limit."""
    timestamp = published_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    cutoff = reference.astimezone(timezone.utc) - timedelta(days=max_age_days)
    return timestamp.astimezone(timezone.utc) >= cutoff
