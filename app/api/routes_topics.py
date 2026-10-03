"""Watchlist topic API, including fast template suggestions."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from app.config import Settings
from app.db import Database
from app.models import TopicCreate
from app.topics.service import TopicLimitError, TopicService
from app.youtube.trend_scheduler import TrendScheduler


class SuggestRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)


def _suggest(name: str, city: str) -> dict[str, object]:
    clean = " ".join(name.split())
    lower = clean.casefold()
    food_signals = (
        "kopi", "teh", "es ", "seblak", "bakso", "mie", "ayam", "cincau",
        "susu", "jus", "roti", "kue", "sambal", "nasi", "burger",
    )
    category = "makanan_minuman" if any(value in lower for value in food_signals) else "umum"
    tokens = [token for token in lower.split() if len(token) >= 3]
    return {
        "keywords": [lower],
        "product_terms": list(dict.fromkeys([lower, *tokens]))[:8],
        "exclude_terms": [],
        "category": category,
        "cities": [city],
        "source": "template",
    }


def create_topics_router(
    database: Database, service: TopicService, scheduler: TrendScheduler,
    settings: Settings,
) -> APIRouter:
    router = APIRouter(prefix="/api/topics", tags=["topics"])

    @router.get("")
    async def topics() -> dict[str, object]:
        items = []
        for topic in await database.list_topics():
            videos = await database.list_videos(topic.id)
            social = await database.social_stats(topic.id)
            marketplace = await database.marketplace_stats(topic.id)
            items.append({
                **topic.model_dump(mode="json"),
                "videos_tracked": len(videos),
                "places_relevant": await database.count_relevant_places(topic.id),
                "social_posts": social["total_posts"],
                "marketplace_products": marketplace["products"],
                "yt_last_snapshot_at": await database.get_last_snapshot_at(topic.id),
                "maps_last_refresh_at": topic.maps_last_refresh_at,
            })
        return {"items": items}

    @router.post("/suggest")
    async def suggest(payload: SuggestRequest) -> dict[str, object]:
        return _suggest(payload.name, settings.default_city)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_topic(
        payload: TopicCreate, background: BackgroundTasks
    ) -> dict[str, object]:
        try:
            topic = await service.create(payload)
        except TopicLimitError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if scheduler.active:
            background.add_task(scheduler.discover_topic, topic)
        return topic.model_dump(mode="json")

    @router.delete("/{topic_id}")
    async def delete_topic(topic_id: str) -> dict[str, bool]:
        if not await database.deactivate_topic(topic_id):
            raise HTTPException(status_code=404, detail="Topik tidak ditemukan")
        return {"deleted": True}

    return router
