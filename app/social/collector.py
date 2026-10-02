"""Collect and locally filter public TikTok/Instagram posts."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.db import Database
from app.events import EventBroker
from app.models import Topic

from .apify_client import Platform, SocialApifyClient
from .parsing import parse_social_items
from .sentiment import SocialSentimentService

logger = logging.getLogger(__name__)


class SocialCollector:
    def __init__(
        self, database: Database, client: SocialApifyClient,
        settings: Settings, broker: EventBroker,
        sentiment: SocialSentimentService | None = None,
    ) -> None:
        self.database = database
        self.client = client
        self.settings = settings
        self.broker = broker
        self.sentiment = sentiment

    async def analyze_pending(self, topic_id: str) -> dict[str, int | str]:
        if self.sentiment is None:
            return {"analyzed": 0, "pending": 0, "analyzer": "disabled"}
        return await self.sentiment.analyze_topic(topic_id)

    async def _collect_platform(
        self, topic: Topic, platform: Platform, captured_at: datetime
    ) -> dict[str, int]:
        cutoff = captured_at - timedelta(days=self.settings.social_lookback_days)
        totals = {"posts": 0, "relevant_posts": 0, "new_posts": 0}
        collection = await self.client.collect(platform, topic)
        parsed = parse_social_items(
            platform, collection.items, topic, now=collection.collected_at
        )
        for post in parsed:
            if post.published_at < cutoff:
                continue
            totals["posts"] += 1
            if post.mentions_product:
                totals["relevant_posts"] += 1
            inserted = await self.database.upsert_social_post(
                platform=platform, post_id=post.post_id, topic_id=topic.id,
                text=post.text, author_name=post.author_name, author_url=post.author_url,
                url=post.url, published_at=post.published_at, seen_at=collection.collected_at,
                query=post.query, mentions_product=post.mentions_product,
                views=post.views, likes=post.likes, comments=post.comments, shares=post.shares,
            )
            if inserted and post.mentions_product:
                totals["new_posts"] += 1
                await self.broker.publish("social_post_new", {
                    "platform": platform,
                    "topic_id": topic.id,
                    "post_id": post.post_id,
                    "text": post.text,
                    "url": post.url,
                    "published_at": post.published_at.isoformat().replace("+00:00", "Z"),
                    "likes": post.likes,
                    "views": post.views,
                })
        await self.database.update_social_refresh(
            topic.id, platform, collection.collected_at
        )
        return totals

    async def refresh_platform(
        self, topic: Topic, platform: Platform, *, now: datetime | None = None
    ) -> dict[str, int]:
        """Refresh one source for a bounded, observable manual retry."""

        if platform not in self.settings.active_sources:
            raise ValueError(f"Sumber {platform} tidak aktif")
        captured_at = now or datetime.now(timezone.utc)
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        totals = await self._collect_platform(topic, platform, captured_at)
        await self.analyze_pending(topic.id)
        await self.broker.publish("social_status", {
            "topic_id": topic.id,
            "platform": platform,
            "status": "active" if totals["relevant_posts"] else "limited",
            "message": f"{totals['relevant_posts']} post relevan dari {platform.title()}",
            "counts": totals,
        })
        return totals

    async def refresh_topic(self, topic: Topic, *, now: datetime | None = None) -> dict[str, int]:
        captured_at = now or datetime.now(timezone.utc)
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        totals = {"posts": 0, "relevant_posts": 0, "new_posts": 0}
        completed = 0
        errors: list[Exception] = []
        platforms: list[Platform] = [
            platform for platform in ("tiktok", "instagram", "facebook")
            if platform in self.settings.active_sources
        ]
        for platform in platforms:
            try:
                counts = await self._collect_platform(topic, platform, captured_at)
            except Exception as exc:
                errors.append(exc)
                logger.warning("Apify %s gagal untuk %s: %s", platform, topic.id, exc)
                continue
            completed += 1
            for key in totals:
                totals[key] += counts[key]

        # Analyze one bounded batch immediately; the scheduler drains remaining
        # pending captions without spending another Apify run.
        await self.analyze_pending(topic.id)

        if completed == 0 and errors:
            raise errors[-1]
        await self.broker.publish("social_status", {
            "topic_id": topic.id,
            "status": "active" if totals["relevant_posts"] else "limited",
            "message": f"{totals['relevant_posts']} post relevan dari TikTok/Instagram/Facebook",
            "counts": totals,
        })
        return totals
