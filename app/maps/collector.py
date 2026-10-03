"""Persist relevant Google Maps places and product opinions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from app.config import Settings
from app.db import Database
from app.events import EventBroker
from app.models import Topic

from .apify_client import ApifyMapsClient
from .parsing import parse_apify_items
from .relevance import place_relevance

logger = logging.getLogger(__name__)


class MapsCollector:
    def __init__(
        self, database: Database, client: ApifyMapsClient,
        settings: Settings, broker: EventBroker,
    ) -> None:
        self.database = database
        self.client = client
        self.settings = settings
        self.broker = broker

    async def refresh_topic(self, topic: Topic, *, now: datetime | None = None) -> dict[str, int]:
        captured_at = now or datetime.now(timezone.utc)
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        await self.database.purge_expired_maps(
            now=captured_at, snapshot_ttl_days=self.settings.maps_content_ttl_days
        )
        total_places = 0
        relevant_places = 0
        new_reviews = 0
        completed_cities = 0
        errors: list[Exception] = []

        for city in topic.cities:
            try:
                collection = await self.client.collect(topic, city)
            except Exception as exc:
                errors.append(exc)
                logger.warning("Apify Maps gagal untuk %s/%s: %s", topic.id, city, exc)
                continue
            completed_cities += 1
            for place in parse_apify_items(collection.items, now=collection.collected_at):
                total_places += 1
                relevant, name_hit, review_hits = place_relevance(place, topic)
                if relevant:
                    relevant_places += 1
                await self.database.upsert_place(
                    topic_id=topic.id,
                    place_id=place.place_id,
                    city=city,
                    is_relevant=relevant,
                    is_own=place.place_id == topic.own_place_id,
                    seen_at=collection.collected_at,
                )
                await self.database.insert_place_snapshot(
                    topic_id=topic.id,
                    place_id=place.place_id,
                    captured_at=collection.collected_at,
                    name=place.name,
                    address=place.address,
                    maps_uri=place.url,
                    primary_type=place.primary_type,
                    business_status=place.business_status,
                    rating=place.rating,
                    user_rating_count=place.user_rating_count,
                    name_mentions_product=name_hit,
                )
                if not relevant:
                    continue
                for review, review_hit in zip(place.reviews, review_hits, strict=False):
                    # A matching business name makes the place relevant, but
                    # it must not turn service/parking reviews into product
                    # opinions. Product feed items need a text-level hit.
                    mentions = bool(review_hit)
                    inserted = await self.database.insert_maps_comment(
                        topic_id=topic.id,
                        place_id=place.place_id,
                        review_id=review.review_id,
                        text=review.text,
                        stars=review.stars,
                        author_name=review.author_name,
                        author_uri=review.author_uri,
                        url=review.url or place.url,
                        created_at=review.created_at,
                        collected_at=collection.collected_at,
                        mentions_product=mentions,
                        category="opini_produk" if mentions else "opini_tempat",
                        expires_at=collection.collected_at + timedelta(days=self.settings.maps_content_ttl_days),
                        max_comment_chars=self.settings.max_comment_chars,
                    )
                    if inserted:
                        new_reviews += 1
                        await self.broker.publish("comment_new", {
                            "id": f"gm_{review.review_id}",
                            "topic_id": topic.id,
                            "source": "gmaps",
                            "place_id": place.place_id,
                            "category": "opini_produk" if mentions else "opini_tempat",
                            "text": review.text,
                            "stars": review.stars,
                            "created_at": review.created_at.isoformat().replace("+00:00", "Z"),
                        })

        if completed_cities == 0 and errors:
            raise errors[-1]
        status = "active" if relevant_places else "limited"
        await self.database.update_topic_maps_refresh(topic.id, captured_at, status=status)
        counts = {
            "places": total_places,
            "relevant_places": relevant_places,
            "new_reviews": new_reviews,
        }
        await self.broker.publish("topic_status", {
            "topic_id": topic.id,
            "status": status,
            "source": "maps_apify",
            "message": f"{relevant_places} tempat relevan, {new_reviews} opini baru",
            "counts": counts,
        })
        return counts
