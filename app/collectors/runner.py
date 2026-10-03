"""Lifecycle dan orkestrasi collector latar belakang."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from app.config import Settings
from app.db import Database
from app.events import EventBroker
from app.models import Comment, CommentIn, Product
from app.products import ProductCatalog

from .filters import is_comment_within_age

if TYPE_CHECKING:
    from .base import BaseCollector

logger = logging.getLogger(__name__)


def build_collectors(settings: Settings, products: Sequence[Product]) -> list[BaseCollector]:
    """Buat hanya collector yang dikenal dan memiliki konfigurasi wajib."""
    collectors: list[BaseCollector] = []
    for source in settings.active_sources:
        if source == "replay":
            from .replay import ReplayCollector

            collectors.append(
                ReplayCollector(
                    settings.seed_comments_path, settings.replay_interval_seconds
                )
            )
        elif source in {"youtube", "youtube_trend"}:
            from .youtube import YouTubeCollector

            if not settings.youtube_api_key:
                logger.warning(
                    "YOUTUBE_API_KEY belum diisi; YouTube memakai fallback halaman publik"
                )
            collectors.append(
                YouTubeCollector(
                    api_key=settings.youtube_api_key,
                    interval_seconds=settings.collect_interval_seconds,
                    videos_per_product=settings.youtube_videos_per_product,
                    search_refresh_minutes=settings.youtube_search_refresh_minutes,
                )
            )
        elif source == "playstore":
            from .playstore import PlayStoreCollector

            if not any(product.playstore_app_ids for product in products):
                logger.warning(
                    "Play Store aktif tetapi tidak ada playstore_app_ids; sumber dilewati"
                )
                continue
            collectors.append(PlayStoreCollector(settings.collect_interval_seconds))
        elif source == "inbox":
            from .inbox import InboxCollector

            collectors.append(
                InboxCollector(settings.inbox_path, settings.collect_interval_seconds)
            )
        else:
            logger.warning("Sumber collector tidak dikenal dan dilewati: %s", source)
    return collectors


class CollectorRunner:
    """Jalankan setiap collector pada task terpisah dan publikasikan data baru."""

    def __init__(
        self,
        settings: Settings,
        products: list[Product] | ProductCatalog,
        database: Database | Any,
        broker: EventBroker,
        collectors: Sequence[BaseCollector] | None = None,
    ) -> None:
        self.settings = settings
        self.products = (
            products.products if isinstance(products, ProductCatalog) else products
        )
        self.database = database
        self.broker = broker
        self.collectors = list(
            collectors
            if collectors is not None
            else build_collectors(settings, self.products)
        )
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def active_sources(self) -> list[str]:
        return [collector.name for collector in self.collectors]

    def start(self) -> None:
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(
                self._run_loop(collector), name=f"collector-{collector.name}"
            )
            for collector in self.collectors
        ]

    async def stop(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(
            *(collector.close() for collector in self.collectors),
            return_exceptions=True,
        )

    async def collect_once(self, collector: BaseCollector) -> list[Comment]:
        """Jalankan satu siklus; berguna untuk runner maupun CLI/debug test."""
        try:
            items = await collector.collect(self.products)
            cleaned = [
                self._truncate(item)
                for item in items
                if item.text.strip()
                and is_comment_within_age(
                    item.created_at, self.settings.comment_max_age_days
                )
            ]
            discarded = len(items) - len(cleaned)
            if discarded:
                logger.info(
                    "%s membuang %d komentar kosong/lebih tua dari %d hari",
                    collector.name,
                    discarded,
                    self.settings.comment_max_age_days,
                )
            inserted = await self._insert(cleaned)
            for comment in inserted:
                await self.broker.publish("comment_new", comment)
            if inserted:
                logger.info(
                    "%s menyimpan %d komentar baru", collector.name, len(inserted)
                )
            return inserted
        except Exception:
            logger.exception("Siklus collector %s gagal", collector.name)
            return []

    def _truncate(self, item: CommentIn) -> CommentIn:
        return item.model_copy(
            update={"text": item.text[: self.settings.max_comment_chars]}
        )

    async def _insert(self, items: list[CommentIn]) -> list[Comment]:
        """Insert through the real Database while remaining easy to fake in tests."""
        insert_many = getattr(self.database, "insert_comments", None)
        if insert_many is not None:
            return await self._call_with_limit(insert_many, items)

        inserted: list[Comment] = []
        insert_one = self.database.insert_comment
        for item in items:
            result = await self._call_with_limit(insert_one, item)
            if isinstance(result, Comment):
                inserted.append(result)
            elif result:
                getter = getattr(self.database, "get_comment", None)
                saved = await getter(item.id) if getter is not None else None
                inserted.append(saved or self._pending_comment(item))
        return inserted

    async def _call_with_limit(
        self, method: Callable[..., Awaitable[Any]], payload: Any
    ) -> Any:
        parameters = inspect.signature(method).parameters
        if "max_comment_chars" in parameters:
            return await method(
                payload, max_comment_chars=self.settings.max_comment_chars
            )
        if "max_chars" in parameters:
            return await method(payload, max_chars=self.settings.max_comment_chars)
        return await method(payload)

    @staticmethod
    def _pending_comment(item: CommentIn) -> Comment:
        return Comment(
            **item.model_dump(),
            collected_at=datetime.now(timezone.utc),
            status="pending",
            sentiment=None,
            score=None,
            topics=[],
            analyzer=None,
            attempts=0,
        )

    async def _run_loop(self, collector: BaseCollector) -> None:
        while True:
            try:
                await self.collect_once(collector)
                await asyncio.sleep(collector.interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Defensive: collect_once already isolates ordinary source failures.
                logger.exception("Loop collector %s pulih dari error", collector.name)
                await asyncio.sleep(collector.interval_seconds)
