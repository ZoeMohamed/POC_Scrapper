"""Small, server-side client for the Apify Google Maps Actor.

The POC deliberately keeps the Apify token out of URLs and browser responses.
An Actor run is counted once against the Maps budget; status and dataset reads
are control-plane calls for that run.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.maps.errors import (
    MapsBadRequestError,
    MapsPermissionError,
    MapsRateLimitedError,
    MapsTransientError,
)
from app.maps.usage import MapsUsageTracker
from app.models import Topic

logger = logging.getLogger(__name__)
APIFY_API_ROOT = "https://api.apify.com/v2"
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMING-OUT", "TIMED-OUT", "ABORTED", "ABORTING"}


@dataclass(frozen=True)
class ApifyCollection:
    run_id: str
    dataset_id: str
    items: list[dict[str, Any]]
    query: str
    city: str
    collected_at: datetime


class ApifyMapsClient:
    """Run and read ``compass/crawler-google-places`` asynchronously."""

    def __init__(
        self,
        settings: Settings,
        usage: MapsUsageTracker,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not settings.apify_maps_token_value:
            raise ValueError("APIFY_MAPS_TOKEN atau APIFY_TOKEN belum diisi")
        self.settings = settings
        self.token = settings.apify_maps_token_value
        self.usage = usage
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.youtube_http_timeout_seconds)
        )
        self._owns_client = client is None

    @property
    def actor_id(self) -> str:
        return self.settings.apify_actor_id

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "umkm-trend-poc/3.1",
        }

    @staticmethod
    def _error_message(response: httpx.Response, fallback: str) -> str:
        try:
            payload = response.json()
            detail = payload.get("error", {}).get("message") or payload.get("message")
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
        """Request JSON with bounded retries and safe error classes."""

        for attempt in range(retries):
            try:
                response = await self._client.request(
                    method,
                    f"{APIFY_API_ROOT}{path}",
                    headers=self._headers(),
                    json=json_payload,
                    params=params,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == retries - 1:
                    raise MapsTransientError("Apify tidak merespons") from exc
                await asyncio.sleep(2**attempt)
                continue

            if response.status_code in {401, 403}:
                detail = self._error_message(response, "Token Apify tidak dapat menjalankan Actor Maps")
                if "monthly usage hard limit" in detail.casefold() or "usage hard limit" in detail.casefold():
                    detail = "Batas penggunaan bulanan Apify tercapai; naikkan hard limit atau gunakan token Apify lain"
                raise MapsPermissionError(detail)
            if response.status_code == 429:
                if attempt == retries - 1:
                    raise MapsRateLimitedError("Apify sedang membatasi request")
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code == 400:
                raise MapsBadRequestError(
                    self._error_message(response, "Input Apify tidak valid")
                )
            if response.status_code >= 500:
                if attempt == retries - 1:
                    raise MapsTransientError("Apify sedang bermasalah")
                await asyncio.sleep(2**attempt)
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise MapsTransientError("Respons Apify tidak valid") from exc
            if not isinstance(payload, (dict, list)):
                raise MapsTransientError("Respons Apify bukan JSON object/list")
            return payload
        raise MapsTransientError("Apify tidak merespons")

    def build_input(self, topic: Topic, city: str) -> dict[str, Any]:
        """Build only documented Actor input fields, with POC safety caps."""

        clean_city = " ".join(city.split()) or self.settings.default_city
        keyword = topic.keywords[0] if topic.keywords else topic.name
        query = " ".join(f"{keyword} {clean_city}".split())
        return {
            "searchStringsArray": [query],
            "locationQuery": clean_city,
            "maxCrawledPlacesPerSearch": min(
                5_000, max(1, self.settings.maps_max_places_per_search)
            ),
            "maxReviews": min(5_000, max(0, self.settings.maps_max_reviews_per_place)),
            # Deliberately omit reviewsStartDate. maps_content_ttl_days controls
            # our cache lifetime, not how old the newest available review may
            # be; low-volume UMKM often have no review in a seven-day window.
            "reviewsSort": "newest",
            "reviewsOrigin": "google",
            "language": self.settings.maps_language,
            "scrapePlaceDetailPage": True,
            # Avoid collecting more personal data than this dashboard needs.
            "scrapeReviewsPersonalData": False,
            "skipClosedPlaces": True,
        }

    async def collect(self, topic: Topic, city: str) -> ApifyCollection:
        started_at = datetime.now(timezone.utc)
        payload = self.build_input(topic, city)
        query = str(payload["searchStringsArray"][0])

        # One Actor run can produce many places/reviews, so the persisted cap
        # is intentionally charged once before the run is created.
        await self.usage.consume("maps_apify_run", 1, now=started_at)
        actor_path = quote(self.actor_id, safe="~")
        try:
            run_payload = await self._request_json(
                "POST", f"/actors/{actor_path}/runs", json_payload=payload
            )
        except Exception:
            await self.usage.refund("maps_apify_run", 1, now=started_at)
            raise
        run_data = run_payload.get("data", {}) if isinstance(run_payload, dict) else {}
        run_id = str(run_data.get("id") or "")
        dataset_id = str(run_data.get("defaultDatasetId") or "")
        if not run_id:
            raise MapsTransientError("Apify tidak mengembalikan run id")

        status_data: dict[str, Any] = run_data
        deadline = asyncio.get_running_loop().time() + self.settings.apify_poll_timeout_seconds
        while True:
            status = str(status_data.get("status") or "").upper()
            if status in TERMINAL_STATUSES:
                break
            if asyncio.get_running_loop().time() >= deadline:
                await self._abort(run_id)
                raise MapsTransientError("Run Apify melewati batas waktu")
            await asyncio.sleep(self.settings.apify_poll_interval_seconds)
            status_payload = await self._request_json("GET", f"/actor-runs/{quote(run_id, safe='')}" )
            status_data = status_payload.get("data", {}) if isinstance(status_payload, dict) else {}
            dataset_id = dataset_id or str(status_data.get("defaultDatasetId") or "")

        final_status = str(status_data.get("status") or "").upper()
        if final_status != "SUCCEEDED":
            detail = str(status_data.get("statusMessage") or final_status or "gagal")
            raise MapsTransientError(f"Run Apify berakhir dengan status {detail}")
        if not dataset_id:
            raise MapsTransientError("Run Apify tidak memiliki dataset")

        items_payload = await self._request_json(
            "GET", f"/datasets/{quote(dataset_id, safe='')}/items",
            params={"clean": "true", "format": "json"},
        )
        if isinstance(items_payload, list):
            raw_items = items_payload
        elif isinstance(items_payload, dict) and isinstance(items_payload.get("data"), list):
            raw_items = items_payload["data"]
        else:
            raw_items = []
        items = [item for item in raw_items if isinstance(item, dict)]
        logger.info("Apify Maps run selesai: %s item untuk %s", len(items), query)
        return ApifyCollection(
            run_id=run_id,
            dataset_id=dataset_id,
            items=items,
            query=query,
            city=city,
            collected_at=datetime.now(timezone.utc),
        )

    async def _abort(self, run_id: str) -> None:
        try:
            await self._request_json("POST", f"/actor-runs/{quote(run_id, safe='')}/abort", retries=1)
        except Exception:
            logger.warning("Run Apify %s tidak dapat dihentikan", run_id)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
