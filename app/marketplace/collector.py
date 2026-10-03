"""Persist Shopee product signals and publish live status events."""

from __future__ import annotations

import logging
from datetime import datetime

from app.config import Settings
from app.db import Database
from app.events import EventBroker
from app.models import Topic

from .apify_client import ShopeeApifyClient
from .parsing import parse_shopee_items

logger = logging.getLogger(__name__)


class MarketplaceCollector:
    def __init__(self, database: Database, client: ShopeeApifyClient, settings: Settings, broker: EventBroker) -> None:
        self.database, self.client, self.settings, self.broker = database, client, settings, broker

    async def refresh_topic(self, topic: Topic, *, now: datetime | None = None) -> dict[str, int]:
        collection = await self.client.collect(topic)
        products = parse_shopee_items(collection.items, topic, query=collection.query)
        inserted = 0
        for product in products:
            if await self.database.upsert_marketplace_product(
                platform="shopee", product_id=product.product_id, topic_id=topic.id,
                title=product.title, description=product.description, url=product.url,
                shop_name=product.shop_name, category=product.category, price=product.price,
                original_price=product.original_price, rating=product.rating,
                rating_count=product.rating_count, sold_count=product.sold_count,
                stock=product.stock, image_url=product.image_url, query=product.query,
                seen_at=collection.collected_at,
            ):
                inserted += 1
        await self.database.update_marketplace_refresh(topic.id, "shopee", collection.collected_at)
        payload = {"topic_id": topic.id, "status": "active" if products else "limited", "source": "apify_shopee", "message": f"{len(products)} produk Shopee relevan", "counts": {"products": len(products), "new_products": inserted}}
        await self.broker.publish("marketplace_status", payload)
        return {"products": len(products), "new_products": inserted}
