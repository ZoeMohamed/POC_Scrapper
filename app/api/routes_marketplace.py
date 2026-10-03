"""Read endpoints for Apify marketplace trend signals."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.db import Database


def create_marketplace_router(database: Database) -> APIRouter:
    router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

    @router.get("/products")
    async def products(
        topic_id: str,
        platform: str = Query(default="shopee", pattern="^shopee$"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        if await database.get_topic(topic_id) is None:
            raise HTTPException(status_code=404, detail="Topik tidak ditemukan")
        items = await database.list_marketplace_products(topic_id, platform=platform, limit=limit)
        return {"items": items, "total": len(items)}

    @router.get("/stats")
    async def stats(
        topic_id: str,
        platform: str = Query(default="shopee", pattern="^shopee$"),
    ) -> dict[str, object]:
        if await database.get_topic(topic_id) is None:
            raise HTTPException(status_code=404, detail="Topik tidak ditemukan")
        return await database.marketplace_stats(topic_id, platform=platform)

    return router
