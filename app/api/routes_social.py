"""Read endpoints for filtered TikTok and Instagram posts."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.db import Database


def create_social_router(database: Database) -> APIRouter:
    router = APIRouter(prefix="/api/social", tags=["social"])

    @router.get("/feed")
    async def feed(
        topic_id: str,
        platform: Literal["tiktok", "instagram", "facebook"] | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        if await database.get_topic(topic_id) is None:
            raise HTTPException(status_code=404, detail="Topik tidak ditemukan")
        items = await database.list_social_posts(topic_id, platform=platform, limit=limit)
        return {"items": items, "total": len(items)}

    @router.get("/stats")
    async def stats(topic_id: str) -> dict[str, object]:
        if await database.get_topic(topic_id) is None:
            raise HTTPException(status_code=404, detail="Topik tidak ditemukan")
        return await database.social_stats(topic_id)

    return router
