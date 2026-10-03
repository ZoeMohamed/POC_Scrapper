"""Comment feed API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.db import Database, to_utc_iso
from app.models import Comment

from .windows import Window, since_for_window


def encode_cursor(comment: Comment) -> str:
    """Encode a stable cursor matching the feed sort tuple."""
    return f"{to_utc_iso(comment.created_at)}|{comment.id}"


def decode_cursor(value: str) -> tuple[datetime, str]:
    """Decode ``<created_at>|<id>`` and reject malformed cursors."""
    try:
        timestamp, comment_id = value.rsplit("|", 1)
        if not timestamp or not comment_id:
            raise ValueError
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc), comment_id
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Cursor before harus berformat <created_at>|<id>",
        ) from exc


def create_feed_router(
    database: Database, default_window: Window = "30d"
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["feed"])

    @router.get("/feed")
    async def get_feed(
        product_id: str | None = None,
        sentiment: Literal["positif", "negatif", "netral", "pending"] | None = None,
        source: str | None = None,
        q: str | None = Query(default=None, max_length=200),
        limit: int = Query(default=50, ge=1, le=200),
        window: Window = Query(default=default_window),
        before: str | None = None,
    ) -> dict[str, object]:
        cursor = decode_cursor(before) if before else None
        items = await database.get_feed(
            product_id=product_id, sentiment=sentiment, source=source, q=q,
            limit=limit, since=since_for_window(window), before=cursor,
        )
        next_before = encode_cursor(items[-1]) if len(items) == limit else None
        return {"items": items, "next_before": next_before}

    return router
