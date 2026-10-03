"""Capture batched video statistics and publish live trend ticks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db import Database
from app.events import EventBroker
from app.models import TrendMetrics, VideoStat

from .trend_discovery import TrendClient
from .trend_metrics import calculate_trend_metrics


class StatsSnapshotService:
    def __init__(
        self, database: Database, client: TrendClient, broker: EventBroker,
        *, usage_bucket: str = "yt_read",
    ) -> None:
        self.database = database
        self.client = client
        self.broker = broker
        self.usage_bucket = usage_bucket

    async def capture(self, topic_id: str, *, now: datetime | None = None) -> TrendMetrics:
        captured = (now or datetime.now(timezone.utc)).replace(microsecond=0)
        videos = await self.database.list_videos(topic_id)
        details: list[dict[str, Any]] = []
        for start in range(0, len(videos), 50):
            details.extend(await self.client.get_videos(
                [item.video_id for item in videos[start:start + 50]],
                usage_bucket=self.usage_bucket,
            ))
        await self.database.insert_video_stats([
            VideoStat(
                video_id=str(item["video_id"]), captured_at=captured,
                views=max(0, int(item.get("views", 0))), likes=item.get("likes"),
                comments=item.get("comments"),
            ) for item in details
        ])
        metrics = calculate_trend_metrics(
            topic_id, videos, await self.database.get_video_stats_rows(topic_id), now=captured
        )
        await self.broker.publish("trend_tick", {
            "topic_id": topic_id,
            "captured_at": captured.isoformat().replace("+00:00", "Z"),
            "views_gain_1h": metrics.views_gain_1h,
            "views_gain_since_last": metrics.views_gain_since_last,
            "videos_tracked": metrics.videos_tracked,
        })
        return metrics
