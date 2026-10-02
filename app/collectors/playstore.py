"""Collector ulasan Google Play Store."""

import asyncio
import logging
from typing import Any

from app.models import CommentIn, Product

from .base import BaseCollector, hash_author

try:
    from google_play_scraper import Sort, reviews
except ImportError:  # replay/inbox remain usable in a minimal installation
    Sort = None  # type: ignore[assignment]
    reviews = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class PlayStoreCollector(BaseCollector):
    name = "playstore"

    def __init__(self, interval_seconds: float = 90.0) -> None:
        self.interval_seconds = interval_seconds

    async def collect(self, products: list[Product]) -> list[CommentIn]:
        comments: list[CommentIn] = []
        for product in products:
            for app_id in product.playstore_app_ids:
                try:
                    raw_reviews = await asyncio.to_thread(self._fetch_reviews, app_id)
                    comments.extend(
                        mapped
                        for review in raw_reviews
                        if (mapped := self._map_review(review, app_id, product.id))
                    )
                except Exception as exc:  # dependency/API errors must not stop runner
                    logger.warning("Play Store %s gagal sementara: %s", app_id, exc)
        return comments

    @staticmethod
    def _fetch_reviews(app_id: str) -> list[dict[str, Any]]:
        if reviews is None or Sort is None:
            raise RuntimeError("Dependency google-play-scraper belum terpasang")
        result, _continuation = reviews(
            app_id,
            lang="id",
            country="id",
            sort=Sort.NEWEST,
            count=50,
        )
        return result

    @staticmethod
    def _map_review(
        review: dict[str, Any], app_id: str, product_id: str
    ) -> CommentIn | None:
        try:
            return CommentIn(
                id=f"gp_{review['reviewId']}",
                source="playstore",
                product_id=product_id,
                text=review["content"],
                url=f"https://play.google.com/store/apps/details?id={app_id}",
                author_hash=hash_author(review.get("userName")),
                created_at=review["at"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Ulasan Play Store tidak valid dilewati: %s", exc)
            return None
