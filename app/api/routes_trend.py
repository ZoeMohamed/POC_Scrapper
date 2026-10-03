"""YouTube trend metrics and video table endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.db import Database
from app.models import TrendMetrics
from app.youtube.trend_metrics import calculate_trend_metrics


def create_trend_router(database: Database) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["trend"])

    async def metrics_for(topic_id: str) -> TrendMetrics:
        if await database.get_topic(topic_id) is None:
            raise HTTPException(404, "Topik tidak ditemukan")
        videos = await database.list_videos(topic_id)
        rows = await database.get_video_stats_rows(topic_id)
        return calculate_trend_metrics(topic_id, videos, rows)

    @router.get("/trend", response_model=TrendMetrics)
    async def trend(topic_id: str) -> TrendMetrics:
        return await metrics_for(topic_id)

    @router.get("/trend/videos")
    async def trend_videos(
        topic_id: str,
        sort: Literal["gain", "views_per_day", "recent"] = "gain",
        type: Literal["review", "resep", "ide_usaha", "lainnya"] | None = Query(default=None),
    ) -> dict[str, object]:
        metrics = await metrics_for(topic_id)
        items = [item for item in metrics.top_videos if type is None or item.content_type == type]
        if sort == "views_per_day":
            items.sort(key=lambda item: item.views_per_day, reverse=True)
        elif sort == "recent":
            items.sort(key=lambda item: item.published_at, reverse=True)
        else:
            items.sort(key=lambda item: (item.gain_24h or -1, item.views_per_day), reverse=True)
        return {"items": items, "total": len(items)}

    return router
