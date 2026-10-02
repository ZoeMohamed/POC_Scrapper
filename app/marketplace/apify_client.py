"""Small, budget-aware client for the public Shopee Apify Actor."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.models import Topic

from .errors import MarketplaceBadRequestError, MarketplacePermissionError, MarketplaceTransientError
from .usage import MarketplaceUsageTracker

logger = logging.getLogger(__name__)
APIFY_API_ROOT = "https://api.apify.com/v2"
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMING-OUT", "TIMED-OUT", "ABORTED", "ABORTING"}


@dataclass(frozen=True)
class MarketplaceCollection:
    platform: str
    run_id: str
    dataset_id: str
    items: list[dict[str, Any]]
    query: str
    collected_at: datetime


class ShopeeApifyClient:
    platform = "shopee"

    def __init__(self, settings: Settings, usage: MarketplaceUsageTracker, *, client: httpx.AsyncClient | None = None) -> None:
        if not settings.apify_marketplace_token_value:
            raise ValueError("APIFY_MARKETPLACE_TOKEN atau APIFY_TOKEN belum diisi")
        self.settings = settings
        self.token = settings.apify_marketplace_token_value
        self.usage = usage
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(settings.youtube_http_timeout_seconds))
        self._owns_client = client is None

    def query_for(self, topic: Topic) -> str:
        values = [topic.name, *topic.keywords, *topic.product_terms]
        return next((" ".join(str(value).split()).strip() for value in values if len(str(value).strip()) >= 2), topic.name)

    def build_input(self, topic: Topic) -> dict[str, Any]:
        return {
            "country": "id", "mode": "keyword", "keyword": self.query_for(topic),
            "sort": "relevancy", "maxProducts": max(1, self.settings.marketplace_results_per_query),
            "fetchDetail": False, "delay": 0.5,
        }

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "umkm-trend-poc/3.3"}

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

    async def _request_json(self, method: str, path: str, *, json_payload: dict[str, Any] | None = None, params: dict[str, Any] | None = None, retries: int = 3) -> dict[str, Any] | list[Any]:
        for attempt in range(retries):
            try:
                response = await self._client.request(method, f"{APIFY_API_ROOT}{path}", headers=self._headers(), json=json_payload, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == retries - 1:
                    raise MarketplaceTransientError("Apify Shopee tidak merespons") from exc
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code in {401, 403}:
                detail = self._message(response, "Token Apify tidak dapat menjalankan Actor Shopee")
                if "monthly usage hard limit" in detail.casefold() or "usage hard limit" in detail.casefold():
                    detail = "Batas penggunaan bulanan Apify tercapai; naikkan hard limit atau gunakan token Apify lain"
                raise MarketplacePermissionError(detail)
            if response.status_code == 400:
                raise MarketplaceBadRequestError(self._message(response, "Input Actor Shopee tidak valid"))
            if response.status_code == 429:
                if attempt == retries - 1:
                    raise MarketplaceTransientError("Apify sedang membatasi request Shopee")
                await asyncio.sleep(2**attempt)
                continue
            if response.status_code >= 500:
                if attempt == retries - 1:
                    raise MarketplaceTransientError("Actor Shopee sedang bermasalah")
                await asyncio.sleep(2**attempt)
                continue
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise MarketplaceTransientError("Respons Actor Shopee tidak valid") from exc
            if not isinstance(payload, (dict, list)):
                raise MarketplaceTransientError("Respons Actor Shopee bukan JSON")
            return payload
        raise MarketplaceTransientError("Apify Shopee tidak merespons")

    async def collect(self, topic: Topic) -> MarketplaceCollection:
        started_at = datetime.now(timezone.utc)
        query = self.query_for(topic)
        payload = self.build_input(topic)
        await self.usage.consume(self.platform, now=started_at)
        actor_path = quote(self.settings.shopee_actor_id, safe="~")
        try:
            started = await self._request_json("POST", f"/acts/{actor_path}/runs", json_payload=payload)
        except Exception:
            await self.usage.refund(self.platform, now=started_at)
            raise
        data = started.get("data", {}) if isinstance(started, dict) else {}
        run_id = str(data.get("id") or "")
        dataset_id = str(data.get("defaultDatasetId") or "")
        if not run_id:
            raise MarketplaceTransientError("Apify tidak mengembalikan Shopee run id")
        status_data: dict[str, Any] = data
        deadline = asyncio.get_running_loop().time() + self.settings.apify_poll_timeout_seconds
        while True:
            status = str(status_data.get("status") or "").upper()
            if status in TERMINAL_STATUSES:
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise MarketplaceTransientError("Run Shopee Apify melewati batas waktu")
            await asyncio.sleep(self.settings.apify_poll_interval_seconds)
            status_payload = await self._request_json("GET", f"/actor-runs/{quote(run_id, safe='')}")
            status_data = status_payload.get("data", {}) if isinstance(status_payload, dict) else {}
            dataset_id = dataset_id or str(status_data.get("defaultDatasetId") or "")
        if str(status_data.get("status") or "").upper() != "SUCCEEDED":
            raise MarketplaceTransientError(f"Run Shopee berakhir dengan status {status_data.get('status') or 'gagal'}")
        if not dataset_id:
            raise MarketplaceTransientError("Run Shopee tidak memiliki dataset")
        output = await self._request_json("GET", f"/datasets/{quote(dataset_id, safe='')}/items", params={"clean": "true", "format": "json"})
        raw_items = output if isinstance(output, list) else output.get("data", []) if isinstance(output, dict) else []
        items = [item for item in raw_items if isinstance(item, dict)]
        logger.info("Apify Shopee selesai: %s item untuk %s", len(items), query)
        return MarketplaceCollection("shopee", run_id, dataset_id, items, query, datetime.now(timezone.utc))

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
