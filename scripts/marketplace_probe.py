"""Run one bounded Shopee Apify probe without writing application data."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.db import Database
from app.marketplace.apify_client import ShopeeApifyClient
from app.marketplace.parsing import parse_shopee_items
from app.marketplace.usage import MarketplaceUsageTracker
from app.models import Topic


async def run(product: str) -> int:
    settings = get_settings()
    if not settings.apify_marketplace_token_value:
        print("APIFY_MARKETPLACE_TOKEN atau APIFY_TOKEN belum diisi; tidak ada request yang dikirim")
        return 2
    topic = Topic(
        id="marketplace-probe", name=product, category="umum",
        keywords=[product], product_terms=[product, *product.split()],
        cities=[settings.default_city], created_at=datetime.now(timezone.utc),
    )
    database = Database(":memory:")
    await database.init()
    usage = MarketplaceUsageTracker(
        database, daily_cap=settings.marketplace_daily_run_cap,
        monthly_cap=settings.marketplace_monthly_run_cap,
    )
    client = ShopeeApifyClient(settings, usage)
    try:
        result = await client.collect(topic)
        products = parse_shopee_items(result.items, topic, query=result.query)
        print(f"provider=apify actor={settings.shopee_actor_id}")
        print(f"platform=shopee run_id={result.run_id} query={result.query}")
        print(f"raw_products={len(result.items)} relevant_products={len(products)}")
        for product_item in products[:10]:
            print(
                f"- {product_item.shop_name or 'toko'} | "
                f"{product_item.rating or 0} rating | {product_item.title[:120]} | "
                f"{product_item.url or ''}"
            )
        status = await usage.status()
        print(f"marketplace_usage_today={status['today']}/{status['daily_limit']}")
        return 0
    except RuntimeError as exc:
        print(f"Apify Shopee gagal: {exc}")
        return 1
    finally:
        await client.close()
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.product)))


if __name__ == "__main__":
    main()
