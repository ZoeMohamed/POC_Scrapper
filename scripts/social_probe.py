"""Run one bounded TikTok/Instagram Apify probe without writing app data.

Examples:
    python scripts/social_probe.py "sepatu lokal" --platform tiktok
    python scripts/social_probe.py "sepatu lokal" --platform instagram
    python scripts/social_probe.py "sepatu lokal" --platform facebook
"""

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
from app.models import Topic
from app.social.apify_client import SocialApifyClient
from app.social.errors import SocialError
from app.social.parsing import parse_social_items
from app.social.usage import SocialUsageTracker


async def run(product: str, platform: str) -> int:
    settings = get_settings()
    if platform not in {"tiktok", "instagram", "facebook"}:
        print("platform harus tiktok, instagram, atau facebook")
        return 2
    if not settings.apify_social_token_value:
        print("APIFY_SOCIAL_TOKEN atau APIFY_TOKEN belum diisi; tidak ada request yang dikirim")
        return 2
    topic = Topic(
        id="social-probe", name=product, category="umum", keywords=[product],
        product_terms=[product, *product.split()], cities=[settings.default_city],
        created_at=datetime.now(timezone.utc),
    )
    database = Database(":memory:")
    await database.init()
    usage = SocialUsageTracker(
        database, daily_cap=settings.social_daily_run_cap,
        monthly_cap=settings.social_monthly_run_cap,
        platform_daily_cap=settings.social_platform_daily_run_cap,
        platform_monthly_cap=settings.social_platform_monthly_run_cap,
    )
    client = SocialApifyClient(settings, usage)
    try:
        result = await client.collect(platform, topic)  # type: ignore[arg-type]
        posts = parse_social_items(platform, result.items, topic, now=result.collected_at)  # type: ignore[arg-type]
        relevant = [post for post in posts if post.mentions_product]
        print(f"provider=apify actor={client.actor_id(platform)}")
        print(f"platform={platform} run_id={result.run_id} queries={result.queries}")
        print(f"raw_posts={len(posts)} relevant_posts={len(relevant)}")
        for post in relevant[:10]:
            print(f"- {post.author_name or 'akun'} | {post.likes or 0} likes | {post.text[:120]} | {post.url or ''}")
        status = await usage.status()
        print(f"social_usage_today={status['today']}/{status['daily_limit']}")
        return 0
    except SocialError as exc:
        print(f"Apify {platform} gagal: {exc}")
        return 1
    finally:
        await client.close()
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("product")
    parser.add_argument("--platform", choices=("tiktok", "instagram", "facebook"), required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.product, args.platform)))


if __name__ == "__main__":
    main()
