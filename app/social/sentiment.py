"""Sentiment bridge for relevant TikTok and Instagram captions."""

from __future__ import annotations

import logging
from typing import Any

from app.analyzer.worker import AnalyzerWorker
from app.db import Database
from app.events import EventBroker

logger = logging.getLogger(__name__)


class SocialSentimentService:
    """Reuse the configured Gemini/lexicon analyzer without mixing social posts into comments."""

    def __init__(
        self, database: Database, worker: AnalyzerWorker, broker: EventBroker,
        *, enabled: bool = True, batch_size: int = 25,
    ) -> None:
        self.database = database
        self.worker = worker
        self.broker = broker
        self.enabled = enabled
        self.batch_size = max(1, batch_size)

    async def analyze_topic(self, topic_id: str) -> dict[str, int | str]:
        if not self.enabled:
            return {"analyzed": 0, "pending": 0, "analyzer": "disabled"}
        pending = await self.database.list_pending_social_posts(
            topic_id, limit=self.batch_size
        )
        if not pending:
            return {"analyzed": 0, "pending": 0, "analyzer": self.worker.active_analyzer}
        lookup: dict[str, dict[str, Any]] = {}
        items: list[tuple[str, str]] = []
        for row in pending:
            key = self._key(row)
            lookup[key] = row
            items.append((key, str(row.get("text") or "")))
        results = await self.worker.analyze_texts(items)
        analyzed = 0
        returned = set()
        for result in results:
            row = lookup.get(result.id)
            if not row:
                continue
            returned.add(result.id)
            await self.database.update_social_sentiment(
                platform=str(row["platform"]), post_id=str(row["post_id"]),
                topic_id=str(row["topic_id"]), sentiment=result.sentiment,
                score=result.score, topics=result.topics, analyzer=self.worker.active_analyzer,
            )
            analyzed += 1
        if not results:
            for row in pending:
                await self.database.mark_social_sentiment_attempt(
                    platform=str(row["platform"]), post_id=str(row["post_id"]),
                    topic_id=str(row["topic_id"]), failed=True,
                )
        elif len(returned) < len(pending):
            for row in pending:
                if self._key(row) not in returned:
                    await self.database.mark_social_sentiment_attempt(
                        platform=str(row["platform"]), post_id=str(row["post_id"]),
                        topic_id=str(row["topic_id"]), failed=False,
                    )
        remaining = len(await self.database.list_pending_social_posts(topic_id, limit=1))
        payload: dict[str, int | str] = {
            "topic_id": topic_id, "analyzed": analyzed, "pending": remaining,
            "analyzer": self.worker.active_analyzer,
        }
        await self.broker.publish("social_sentiment_updated", payload)
        return payload

    @staticmethod
    def _key(row: dict[str, Any]) -> str:
        return f"{row['platform']}:{row['topic_id']}:{row['post_id']}"

