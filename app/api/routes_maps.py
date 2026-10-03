"""Read endpoints for the Apify-backed Google Maps collection."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.db import Database


def create_maps_router(database: Database) -> APIRouter:
    router = APIRouter(prefix="/api/maps", tags=["maps"])

    @router.get("/places")
    async def places(topic_id: str) -> dict[str, object]:
        if await database.get_topic(topic_id) is None:
            raise HTTPException(status_code=404, detail="Topik tidak ditemukan")
        items = await database.list_places_latest(topic_id)
        return {"items": items, "total": len(items)}

    @router.get("/feed")
    async def feed(
        topic_id: str,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, object]:
        if await database.get_topic(topic_id) is None:
            raise HTTPException(status_code=404, detail="Topik tidak ditemukan")
        items = await database.get_topic_feed(topic_id, limit=limit)
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "total": len(items),
        }

    return router


def create_places_compat_router(database: Database) -> APIRouter:
    """Compatibility alias for the path used in the original v3 spec."""
    router = APIRouter(prefix="/api", tags=["maps"])

    @router.get("/places")
    async def places(topic_id: str) -> dict[str, object]:
        if await database.get_topic(topic_id) is None:
            raise HTTPException(status_code=404, detail="Topik tidak ditemukan")
        items = await database.list_places_latest(topic_id)
        return {"items": items, "total": len(items)}

    return router
