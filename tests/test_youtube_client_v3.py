from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.db import Database
from app.youtube.client import YouTubeClient
from app.youtube.quota import QuotaTracker


@pytest.mark.asyncio
async def test_official_client_retries_transient_and_counts_each_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = Database(tmp_path / "client.db"); await database.init()
    tracker = QuotaTracker(database)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": {"message": "temporary"}})
        return httpx.Response(200, json={"items": [{"id": "abc", "snippet": {"title": "Video"}, "statistics": {"viewCount": "12"}}]})

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.youtube.client.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = YouTubeClient("secret", tracker, client=http)
        result = await client.get_videos(["abc"])
    assert result[0]["views"] == 12
    assert calls == 2
    assert (await tracker.status())["buckets"]["yt_read"] == 2
    await database.close()
