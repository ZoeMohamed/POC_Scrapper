"""Topic validation and persistence service."""

from __future__ import annotations

from app.config import Settings
from app.db import Database
from app.models import Topic, TopicCreate


class TopicLimitError(RuntimeError):
    pass


class TopicService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    async def seed(self) -> int:
        return await self.database.seed_topics(self.settings.topics_path)

    async def create(self, data: TopicCreate) -> Topic:
        if await self.database.count_active_topics() >= self.settings.max_active_topics:
            raise TopicLimitError(
                f"Maksimal {self.settings.max_active_topics} topik aktif"
            )
        return await self.database.create_topic(data)
