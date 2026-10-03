"""Probe Apify Google Maps without writing to the application database.

Usage:
    python scripts/maps_probe.py "sepatu lokal" --city Bandung
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from app.config import get_settings
from app.db import Database
from app.maps.apify_client import ApifyMapsClient
from app.maps.parsing import parse_apify_items
from app.maps.relevance import place_relevance
from app.maps.usage import MapsUsageTracker
from app.maps.errors import MapsError
from app.models import Topic


async def run(product: str, city: str) -> int:
    settings = get_settings()
    if settings.maps_provider != "apify":
        print(f"MAPS_PROVIDER={settings.maps_provider}; probe ini khusus Apify")
        return 2
    if not settings.apify_token:
        print("APIFY_TOKEN belum diisi; tidak ada request yang dikirim")
        return 2
    topic = Topic(
        id="probe",
        name=product,
        category="umum",
        keywords=[product],
        product_terms=[product, *product.split()[:5]],
        cities=[city],
        created_at=datetime.now(timezone.utc),
    )
    database = Database(":memory:")
    await database.init()
    usage = MapsUsageTracker(
        database,
        daily_cap=settings.maps_daily_request_cap,
        monthly_cap=settings.maps_monthly_request_cap,
    )
    client = ApifyMapsClient(settings, usage)
    try:
        result = await client.collect(topic, city)
        places = parse_apify_items(result.items, now=result.collected_at)
        relevant = [place for place in places if place_relevance(place, topic)[0]]
        print(f"provider=apify actor={settings.apify_actor_id}")
        print(f"run_id={result.run_id} query={result.query!r} raw_places={len(places)}")
        print(f"relevant_places={len(relevant)} reviews={sum(len(place.reviews) for place in relevant)}")
        for place in relevant:
            print(f"- {place.name} | rating={place.rating} | reviews={len(place.reviews)} | {place.url or ''}")
        status = await usage.status()
        print(f"maps_usage_today={status['today']}/{status['daily_limit']}")
        return 0
    except MapsError as exc:
        print(f"Apify Maps gagal: {exc}")
        return 1
    finally:
        await client.close()
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product")
    parser.add_argument("--city", default=None)
    args = parser.parse_args()
    settings = get_settings()
    raise SystemExit(asyncio.run(run(args.product, args.city or settings.default_city)))


if __name__ == "__main__":
    main()
