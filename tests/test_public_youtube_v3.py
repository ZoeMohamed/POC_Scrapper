from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.youtube.client import PublicYouTubeClient


@pytest.mark.asyncio
async def test_public_client_refreshes_live_view_count() -> None:
    player = {"videoDetails": {"title": "Review Seblak", "shortDescription": "produk seblak", "channelId": "channel", "author": "UMKM TV", "viewCount": "250", "isLiveContent": False}, "microformat": {"playerMicroformatRenderer": {"publishDate": "2026-09-29"}}}
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, text=f"<script>var ytInitialPlayerResponse = {json.dumps(player)};</script>"))
    async with httpx.AsyncClient(transport=transport) as http:
        client = PublicYouTubeClient(client=http)
        client._cache["abc"] = {"video_id": "abc", "title": "lama", "description": "", "channel_id": "", "channel_title": "", "published_at": "2026-09-29T00:00:00+00:00", "live_broadcast_content": "none", "views": 100, "likes": None, "comments": None}
        client._refreshed_at["abc"] = datetime.now(timezone.utc) - timedelta(minutes=2)
        result = await client.get_videos(["abc"])
        assert result[0]["views"] == 250
        assert result[0]["title"] == "Review Seblak"
