"""Background orchestration for discovery and trend snapshots."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.db import Database
from app.events import EventBroker
from app.maps.collector import MapsCollector
from app.models import Topic
from app.social.collector import SocialCollector
from app.marketplace.collector import MarketplaceCollector

from .stats_snapshot import StatsSnapshotService
from .trend_discovery import TrendDiscovery

logger = logging.getLogger(__name__)


class TrendScheduler:
    def __init__(
        self, settings: Settings, database: Database, broker: EventBroker,
        discovery: TrendDiscovery | None, snapshot: StatsSnapshotService | None,
        maps_collector: MapsCollector | None = None,
        social_collector: SocialCollector | None = None,
        marketplace_collector: MarketplaceCollector | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.broker = broker
        self.discovery = discovery
        self.snapshot = snapshot
        self.maps_collector = maps_collector
        self.social_collector = social_collector
        self.marketplace_collector = marketplace_collector
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def active(self) -> bool:
        youtube_active = self.discovery is not None and "youtube_trend" in self.settings.active_sources
        maps_active = self.maps_collector is not None and "maps" in self.settings.active_sources
        social_active = self.social_collector is not None and bool(
            {"tiktok", "instagram", "facebook"}.intersection(self.settings.active_sources)
        )
        marketplace_active = self.marketplace_collector is not None and "shopee" in self.settings.active_sources
        return bool(youtube_active or maps_active or social_active or marketplace_active)

    def start(self) -> None:
        if self.active and self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self.run(), name="youtube-trend-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def discover_topic(self, topic: Topic) -> None:
        if not (
            (self.discovery and self.snapshot and "youtube_trend" in self.settings.active_sources)
            or (self.maps_collector and "maps" in self.settings.active_sources)
            or (self.social_collector and {"tiktok", "instagram", "facebook"}.intersection(self.settings.active_sources))
            or (self.marketplace_collector and "shopee" in self.settings.active_sources)
        ):
            return
        lock = self._locks.setdefault(topic.id, asyncio.Lock())
        if lock.locked():
            return
        async with lock:
            if self.discovery and self.snapshot and "youtube_trend" in self.settings.active_sources:
                try:
                    result = await self.discovery.discover(topic)
                    metrics = await self.snapshot.capture(topic.id)
                    await self.broker.publish("topic_status", {
                        "topic_id": topic.id,
                        "status": "active" if result.stored else "limited",
                        "source": "youtube_trend",
                        "message": f"{result.stored} video tren ditemukan",
                        "counts": {"videos": metrics.videos_tracked},
                    })
                except Exception as exc:
                    logger.exception("Discovery tren gagal untuk %s", topic.id)
                    await self.broker.publish("topic_status", {
                        "topic_id": topic.id, "status": "limited", "source": "youtube_trend",
                        "message": str(exc), "counts": {"videos": 0},
                    })
            if self.maps_collector and "maps" in self.settings.active_sources:
                try:
                    await self.maps_collector.refresh_topic(topic)
                except Exception as exc:
                    logger.exception("Refresh Maps gagal untuk %s", topic.id)
                    await self.broker.publish("topic_status", {
                        "topic_id": topic.id, "status": "limited", "source": "maps_apify",
                        "message": str(exc), "counts": {"relevant_places": 0, "new_reviews": 0},
                    })
            if self.social_collector and {"tiktok", "instagram", "facebook"}.intersection(self.settings.active_sources):
                try:
                    await self.social_collector.refresh_topic(topic)
                except Exception as exc:
                    logger.exception("Refresh sosial gagal untuk %s", topic.id)
                    await self.broker.publish("social_status", {
                        "topic_id": topic.id, "status": "limited", "source": "apify_social",
                        "message": str(exc), "counts": {"relevant_posts": 0, "new_posts": 0},
                    })
            if self.marketplace_collector and "shopee" in self.settings.active_sources:
                try:
                    await self.marketplace_collector.refresh_topic(topic)
                except Exception as exc:
                    logger.exception("Refresh Shopee gagal untuk %s", topic.id)
                    await self.broker.publish("marketplace_status", {
                        "topic_id": topic.id, "status": "limited", "source": "apify_shopee",
                        "message": str(exc), "counts": {"products": 0, "new_products": 0},
                    })

    async def run(self) -> None:
        while not self._stop.is_set():
            now = datetime.now(timezone.utc)
            topics = await self.database.list_topics()
            for topic in topics:
                if self.social_collector:
                    try:
                        await self.social_collector.analyze_pending(topic.id)
                    except Exception:
                        logger.exception("Analisis sentimen sosial gagal untuk %s", topic.id)
                yt_stale = (
                    topic.yt_last_discovery_at is None
                    or topic.yt_last_discovery_at <= now - timedelta(hours=self.settings.yt_search_refresh_hours)
                )
                maps_stale = (
                    self.maps_collector is not None
                    and "maps" in self.settings.active_sources
                    and (
                        topic.maps_last_refresh_at is None
                        or topic.maps_last_refresh_at <= now - timedelta(hours=self.settings.maps_refresh_hours)
                    )
                )
                social_stale = False
                if self.social_collector:
                    for platform in ("tiktok", "instagram", "facebook"):
                        if platform not in self.settings.active_sources:
                            continue
                        last_social = await self.database.get_social_last_refresh(topic.id, platform)
                        if last_social is None or last_social <= now - timedelta(hours=self.settings.social_refresh_hours):
                            social_stale = True
                            break
                marketplace_stale = False
                if self.marketplace_collector and "shopee" in self.settings.active_sources:
                    last_marketplace = await self.database.get_marketplace_last_refresh(topic.id, "shopee")
                    marketplace_stale = last_marketplace is None or last_marketplace <= now - timedelta(hours=self.settings.marketplace_refresh_hours)
                if (self.discovery and yt_stale) or maps_stale or social_stale or marketplace_stale:
                    await self.discover_topic(topic)
                    continue
                if self.snapshot:
                    last = await self.database.get_last_snapshot_at(topic.id)
                    seconds = (
                        self.settings.demo_stats_interval_seconds
                        if self.settings.demo_mode else self.settings.yt_stats_interval_minutes * 60
                    )
                    if last is None or last <= now - timedelta(seconds=seconds):
                        try:
                            await self.snapshot.capture(topic.id)
                        except Exception:
                            logger.exception("Snapshot tren gagal untuk %s", topic.id)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
