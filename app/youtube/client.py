"""YouTube Data API client plus a read-only public fallback for the local POC."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import quote_plus

import httpx

from .errors import (
    YouTubePermissionError, YouTubeQuotaExceededError, YouTubeTransientError,
)
from .parsing import parse_count, relative_datetime, text_value, walk
from .quota import QuotaTracker

logger = logging.getLogger(__name__)
API_ROOT = "https://www.googleapis.com/youtube/v3"
WEB_ROOT = "https://www.youtube.com"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36"


class YouTubeClient:
    mode = "api"

    def __init__(
        self, api_key: str, tracker: QuotaTracker, *, timeout: float = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY belum diisi")
        self.api_key = api_key
        self.tracker = tracker
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def _get(self, path: str, params: dict[str, Any], *, api: str, units: int) -> dict[str, Any]:
        safe_params = {**params, "key": self.api_key}
        for attempt in range(3):
            await self.tracker.consume(api, units)
            try:
                response = await self._client.get(f"{API_ROOT}/{path}", params=safe_params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 2:
                    raise YouTubeTransientError("YouTube tidak merespons") from exc
                await asyncio.sleep(2 ** attempt)
                continue
            reason = ""
            try:
                reason = str(response.json().get("error", {}).get("errors", [{}])[0].get("reason", ""))
            except (ValueError, AttributeError, IndexError):
                pass
            if response.status_code == 429 or (
                response.status_code == 403 and reason in {
                    "quotaExceeded", "dailyLimitExceeded", "userRateLimitExceeded",
                }
            ):
                raise YouTubeQuotaExceededError("Kuota YouTube dari Google habis")
            if response.status_code in {401, 403}:
                raise YouTubePermissionError("YouTube API key tidak memiliki izin")
            if response.status_code >= 500:
                if attempt == 2:
                    raise YouTubeTransientError("YouTube sedang bermasalah")
                await asyncio.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        raise YouTubeTransientError("YouTube tidak merespons")

    async def search_videos(
        self, query: str, order: Literal["date", "viewCount"],
        published_after: datetime, max_results: int = 50,
        page_token: str | None = None,
    ) -> tuple[list[str], str | None]:
        params: dict[str, Any] = {
            "part": "snippet", "q": query, "type": "video", "order": order,
            "publishedAfter": published_after.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "regionCode": "ID", "relevanceLanguage": "id", "safeSearch": "moderate",
            "maxResults": min(50, max_results),
        }
        if page_token:
            params["pageToken"] = page_token
        payload = await self._get("search", params, api="yt_search", units=100)
        ids = [
            str(item.get("id", {}).get("videoId"))
            for item in payload.get("items", []) if item.get("id", {}).get("videoId")
        ]
        return ids, payload.get("nextPageToken")

    async def get_videos(
        self, ids: list[str], parts: str = "snippet,statistics",
        usage_bucket: Literal["yt_read", "yt_demo"] = "yt_read",
    ) -> list[dict[str, Any]]:
        if not ids:
            return []
        payload = await self._get(
            "videos", {"part": parts, "id": ",".join(ids[:50])},
            api=usage_bucket, units=1,
        )
        return [self._normalize_api_item(item) for item in payload.get("items", [])]

    @staticmethod
    def _normalize_api_item(item: dict[str, Any]) -> dict[str, Any]:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        return {
            "video_id": str(item.get("id", "")),
            "title": str(snippet.get("title", "")),
            "description": str(snippet.get("description", "")),
            "channel_id": str(snippet.get("channelId", "")),
            "channel_title": str(snippet.get("channelTitle", "")),
            "published_at": snippet.get("publishedAt"),
            "live_broadcast_content": snippet.get("liveBroadcastContent", "none"),
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats["likeCount"]) if "likeCount" in stats else None,
            "comments": int(stats["commentCount"]) if "commentCount" in stats else None,
        }

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class PublicYouTubeClient:
    """Best-effort public search used when the user has not supplied an API key."""

    mode = "public"

    def __init__(self, *, timeout: float = 15, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._cache: dict[str, dict[str, Any]] = {}
        self._refreshed_at: dict[str, datetime] = {}

    @staticmethod
    def _initial_data(html: str, markers: tuple[str, ...]) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        for marker in markers:
            index = html.find(marker)
            if index >= 0:
                parsed, _ = decoder.raw_decode(html[index + len(marker):].lstrip())
                if isinstance(parsed, dict):
                    return parsed
        raise ValueError("Data awal YouTube tidak ditemukan")

    async def search_videos(
        self, query: str, order: Literal["date", "viewCount"],
        published_after: datetime, max_results: int = 50,
        page_token: str | None = None,
    ) -> tuple[list[str], str | None]:
        del published_after, page_token
        # Public search is best-effort. Sort the discovery pass by upload date
        # and the popularity pass by view count; the cutoff is enforced locally.
        sort_filter = "CAI%3D" if order == "date" else "CAMSAhAB"
        response = await self._client.get(
            f"{WEB_ROOT}/results?search_query={quote_plus(query)}&hl=id&gl=ID&sp={sort_filter}",
            headers={"User-Agent": USER_AGENT, "Accept-Language": "id-ID,id;q=0.9"},
        )
        response.raise_for_status()
        data = self._initial_data(
            response.text,
            ("var ytInitialData = ", "window['ytInitialData'] = ", "ytInitialData = "),
        )
        ids: list[str] = []
        now = datetime.now(timezone.utc)
        for node in walk(data):
            renderer = node.get("videoRenderer")
            if not isinstance(renderer, dict) or not renderer.get("videoId"):
                continue
            video_id = str(renderer["videoId"])
            if video_id in ids:
                continue
            published = relative_datetime(renderer.get("publishedTimeText"), now=now)
            badges = " ".join(text_value(item) for item in renderer.get("badges", []))
            broadcast = (
                "upcoming" if renderer.get("upcomingEventData")
                else "live" if "live" in badges.casefold() else "none"
            )
            self._cache[video_id] = {
                "video_id": video_id,
                "title": text_value(renderer.get("title")),
                "description": text_value(renderer.get("descriptionSnippet")),
                "channel_id": str((renderer.get("ownerText", {}).get("runs") or [{}])[0].get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "")),
                "channel_title": text_value(renderer.get("ownerText")),
                "published_at": published.isoformat(),
                "live_broadcast_content": broadcast,
                "views": parse_count(renderer.get("viewCountText")),
                "likes": None,
                "comments": None,
            }
            self._refreshed_at[video_id] = now
            ids.append(video_id)
            if len(ids) >= min(max_results, 20):
                break
        return ids, None

    async def get_videos(
        self, ids: list[str], parts: str = "snippet,statistics",
        usage_bucket: Literal["yt_read", "yt_demo"] = "yt_read",
    ) -> list[dict[str, Any]]:
        del parts, usage_bucket
        now = datetime.now(timezone.utc)
        stale = [
            video_id for video_id in ids
            if video_id not in self._cache
            or self._refreshed_at.get(video_id, now - timedelta(days=1)) <= now - timedelta(seconds=30)
        ]
        semaphore = asyncio.Semaphore(4)

        async def refresh(video_id: str) -> None:
            async with semaphore:
                try:
                    await self._refresh_video(video_id, now)
                except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                    logger.warning("Statistik publik YouTube gagal diperbarui untuk %s", video_id)

        if stale:
            await asyncio.gather(*(refresh(video_id) for video_id in stale))
        return [self._cache[video_id] for video_id in ids if video_id in self._cache]

    async def _refresh_video(self, video_id: str, captured_at: datetime) -> None:
        response = await self._client.get(
            f"{WEB_ROOT}/watch?v={video_id}&hl=id&gl=ID",
            headers={"User-Agent": USER_AGENT, "Accept-Language": "id-ID,id;q=0.9"},
        )
        response.raise_for_status()
        player = self._initial_data(
            response.text,
            ("var ytInitialPlayerResponse = ", "ytInitialPlayerResponse = "),
        )
        details = player.get("videoDetails", {})
        microformat = player.get("microformat", {}).get("playerMicroformatRenderer", {})
        previous = self._cache.get(video_id, {})
        published = microformat.get("publishDate") or microformat.get("uploadDate") or previous.get("published_at")
        self._cache[video_id] = {
            "video_id": video_id,
            "title": str(details.get("title") or previous.get("title", "")),
            "description": str(details.get("shortDescription") or previous.get("description", "")),
            "channel_id": str(details.get("channelId") or previous.get("channel_id", "")),
            "channel_title": str(details.get("author") or previous.get("channel_title", "")),
            "published_at": published or captured_at.isoformat(),
            "live_broadcast_content": "live" if details.get("isLiveContent") else "none",
            "views": max(0, int(details.get("viewCount") or previous.get("views", 0))),
            "likes": previous.get("likes"),
            "comments": previous.get("comments"),
        }
        self._refreshed_at[video_id] = captured_at

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
