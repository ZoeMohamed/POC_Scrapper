"""One efficient Apify client for TikTok and Instagram post discovery."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote

import httpx

from app.config import Settings
from app.models import Topic

from .errors import (
    SocialBadRequestError,
    SocialPermissionError,
    SocialRateLimitedError,
    SocialTransientError,
)
from .usage import SocialUsageTracker

logger = logging.getLogger(__name__)
APIFY_API_ROOT = "https://api.apify.com/v2"
TERMINAL_STATUSES = {
    "SUCCEEDED", "FAILED", "TIMING-OUT", "TIMED-OUT", "ABORTED", "ABORTING",
}
Platform = Literal["tiktok", "instagram", "facebook"]


@dataclass(frozen=True)
class SocialCollection:
    platform: Platform
    run_id: str
    dataset_id: str
    items: list[dict[str, Any]]
    queries: list[str]
    collected_at: datetime


class SocialApifyClient:
    def __init__(
        self,
        settings: Settings,
        usage: SocialUsageTracker,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not settings.apify_social_token_value:
            raise ValueError("APIFY_SOCIAL_TOKEN atau APIFY_TOKEN belum diisi")
        self.settings = settings
        self.token = settings.apify_social_token_value
        self.usage = usage
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.youtube_http_timeout_seconds)
        )
        self._owns_client = client is None

    def actor_id(self, platform: Platform) -> str:
        if platform == "tiktok":
            return self.settings.tiktok_actor_id
        if platform == "instagram":
            return self.settings.instagram_actor_id
        return self.settings.facebook_actor_id

    def queries_for(self, topic: Topic) -> list[str]:
        values = [*topic.keywords, *topic.product_terms, topic.name]
        seen: set[str] = set()
        queries: list[str] = []
        for value in values:
            clean = " ".join(str(value).split()).strip()
            if len(clean) < 2:
                continue
            key = clean.casefold()
            if key in seen:
                continue
            seen.add(key)
            queries.append(clean)
            if len(queries) >= self.settings.social_max_queries_per_topic:
                break
        return queries or [topic.name]

    def build_input(self, platform: Platform, topic: Topic) -> dict[str, Any]:
        queries = self.queries_for(topic)
        limit = max(1, self.settings.social_results_per_query)
        if platform == "tiktok":
            return {
                "searchQueries": queries,
                "searchSection": "/video",
                "resultsPerPage": limit,
                "maxFollowersPerProfile": 0,
                "maxFollowingPerProfile": 0,
                "commentsPerPost": 0,
                "topLevelCommentsPerPost": 0,
                "maxRepliesPerComment": 0,
                "scrapeRelatedSearchWords": False,
                "scrapeRelatedVideos": False,
                "scrapeAdditionalAuthorMeta": False,
                "shouldDownloadVideos": False,
                "shouldDownloadCovers": False,
                "shouldDownloadSlideshowImages": False,
                "shouldDownloadAvatars": False,
                "shouldDownloadMusicCovers": False,
                "downloadSubtitlesOptions": "NEVER_DOWNLOAD_SUBTITLES",
                "aiVideoDescription": False,
                "aiVideoSummary": False,
                "proxyCountryCode": "ID",
            }
        if platform == "facebook":
            return {
                "categories": queries,
                "locations": topic.cities[:1],
                "searchType": "posts",
                "resultsLimit": max(1, self.settings.facebook_results_per_query),
            }
        tags = [
            "https://www.instagram.com/explore/tags/"
            + "".join(character for character in query.casefold() if character.isalnum())
            + "/"
            for query in queries
        ]
        return {
            "resultsType": "posts",
            "directUrls": list(dict.fromkeys(tags)),
            "resultsLimit": limit,
            "onlyPostsNewerThan": f"{max(1, self.settings.social_lookback_days)} days",
            "addParentData": True,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "umkm-trend-poc/3.2",
        }

    @staticmethod
    def _message(response: httpx.Response, fallback: str) -> str:
        try:
            body = response.json()
            detail = body.get("error", {}).get("message") or body.get("message")
            if detail:
                return str(detail)[:240]
        except (ValueError, AttributeError):
            pass
        return fallback

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any] | list[Any]:
        for attempt in range(retries):
            try:
                response = await self._client.request(
                    method, f"{APIFY_API_ROOT}{path}", headers=self._headers(),
                    json=json_payload, params=params,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == retries - 1:
                    raise SocialTransientError("Apify sosial tidak merespons") from exc
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code in {401, 403}:
                detail = self._message(response, "Token Apify tidak dapat menjalankan Actor sosial")
                if "monthly usage hard limit" in detail.casefold() or "usage hard limit" in detail.casefold():
                    detail = "Batas penggunaan bulanan Apify tercapai; naikkan hard limit atau gunakan token Apify lain"
                raise SocialPermissionError(detail)
            if response.status_code == 429:
                if attempt == retries - 1:
                    raise SocialRateLimitedError("Apify sedang membatasi sosial request")
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code == 400:
                raise SocialBadRequestError(self._message(response, "Input Actor sosial tidak valid"))
            if response.status_code >= 500:
                if attempt == retries - 1:
                    raise SocialTransientError("Actor sosial sedang bermasalah")
                await asyncio.sleep(2**attempt)
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise SocialTransientError("Respons Actor sosial tidak valid") from exc
            if not isinstance(payload, (dict, list)):
                raise SocialTransientError("Respons Actor sosial bukan JSON")
            return payload
        raise SocialTransientError("Apify sosial tidak merespons")

    async def collect(self, platform: Platform, topic: Topic) -> SocialCollection:
        started_at = datetime.now(timezone.utc)
        payload = self.build_input(platform, topic)
        queries = self.queries_for(topic)
        await self.usage.consume(platform, now=started_at)
        actor_path = quote(self.actor_id(platform), safe="~")
        try:
            started = await self._request_json(
                "POST", f"/actors/{actor_path}/runs", json_payload=payload
            )
        except Exception:
            await self.usage.refund(platform, now=started_at)
            raise
        data = started.get("data", {}) if isinstance(started, dict) else {}
        run_id = str(data.get("id") or "")
        dataset_id = str(data.get("defaultDatasetId") or "")
        if not run_id:
            raise SocialTransientError("Apify tidak mengembalikan social run id")

        status_data: dict[str, Any] = data
        deadline = asyncio.get_running_loop().time() + self.settings.apify_poll_timeout_seconds
        while True:
            status = str(status_data.get("status") or "").upper()
            if status in TERMINAL_STATUSES:
                break
            if asyncio.get_running_loop().time() >= deadline:
                await self._abort(run_id)
                raise SocialTransientError("Run sosial Apify melewati batas waktu")
            await asyncio.sleep(self.settings.apify_poll_interval_seconds)
            status_payload = await self._request_json(
                "GET", f"/actor-runs/{quote(run_id, safe='')}"
            )
            status_data = status_payload.get("data", {}) if isinstance(status_payload, dict) else {}
            dataset_id = dataset_id or str(status_data.get("defaultDatasetId") or "")

        if str(status_data.get("status") or "").upper() != "SUCCEEDED":
            raise SocialTransientError(
                f"Run {platform} berakhir dengan status {status_data.get('status') or 'gagal'}"
            )
        if not dataset_id:
            raise SocialTransientError("Run sosial tidak memiliki dataset")
        output = await self._request_json(
            "GET", f"/datasets/{quote(dataset_id, safe='')}/items",
            params={"clean": "true", "format": "json"},
        )
        raw_items = (
            output if isinstance(output, list)
            else output.get("data", []) if isinstance(output, dict) else []
        )
        items = [item for item in raw_items if isinstance(item, dict)]
        logger.info("Apify %s selesai: %s item, %s query", platform, len(items), len(queries))
        return SocialCollection(
            platform=platform, run_id=run_id, dataset_id=dataset_id,
            items=items, queries=queries, collected_at=datetime.now(timezone.utc),
        )

    async def _abort(self, run_id: str) -> None:
        try:
            await self._request_json("POST", f"/actor-runs/{quote(run_id, safe='')}/abort", retries=1)
        except Exception:
            logger.warning("Run sosial Apify %s tidak dapat dihentikan", run_id)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
