"""Unit coverage for the keyless public YouTube fallback."""

from datetime import datetime, timezone

import pytest

from app.collectors.runner import build_collectors
from app.collectors.youtube import YouTubeCollector
from app.config import Settings
from app.models import Product


def test_extract_initial_data() -> None:
    html = '<script>var ytInitialData = {"answer":42};</script>'

    assert YouTubeCollector._extract_initial_data(html) == {"answer": 42}


def test_map_public_comment_hashes_author_and_keeps_source_link() -> None:
    payload = {
        "properties": {
            "commentId": "real-comment-id",
            "content": {"content": "Gula arennya enak dan tidak terlalu manis"},
            "publishedTime": "11 bulan yang lalu",
        },
        "author": {
            "channelId": "private-channel-id",
            "displayName": "Nama tidak boleh disimpan",
        },
    }

    before = datetime.now(timezone.utc)
    comment = YouTubeCollector._map_public_comment(
        payload, "video-id", "kopi-aren"
    )

    assert comment is not None
    assert comment.id == "yt_real-comment-id"
    assert comment.source == "youtube"
    assert comment.product_id == "kopi-aren"
    assert comment.url == (
        "https://www.youtube.com/watch?v=video-id&lc=real-comment-id"
    )
    assert comment.author_hash
    assert "private-channel-id" not in comment.author_hash
    age_days = (before - comment.created_at).days
    assert 329 <= age_days <= 331


@pytest.mark.asyncio
async def test_youtube_source_works_without_api_key() -> None:
    settings = Settings(sources="youtube", youtube_api_key="")
    products = [
        Product(
            id="kopi-aren",
            name="Kopi Susu Gula Aren",
            keywords=["kopi susu gula aren"],
        )
    ]

    collectors = build_collectors(settings, products)
    try:
        assert len(collectors) == 1
        assert isinstance(collectors[0], YouTubeCollector)
        assert collectors[0].name == "youtube"
    finally:
        await collectors[0].close()
