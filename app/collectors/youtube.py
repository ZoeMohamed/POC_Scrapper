"""YouTube comment collector with API v3 and a public-page fallback."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.models import CommentIn, Product

from .base import BaseCollector, hash_author

logger = logging.getLogger(__name__)
API_ROOT = "https://www.googleapis.com/youtube/v3"
YOUTUBE_ROOT = "https://www.youtube.com"
WEB_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36"
)


class YouTubeCollector(BaseCollector):
    name = "youtube"

    def __init__(
        self,
        api_key: str = "",
        interval_seconds: float = 90.0,
        videos_per_product: int = 5,
        search_refresh_minutes: int = 60,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.interval_seconds = interval_seconds
        self.videos_per_product = videos_per_product
        self.refresh_delta = timedelta(minutes=search_refresh_minutes)
        self._client = client or httpx.AsyncClient(timeout=20.0)
        self._owns_client = client is None
        self._video_cache: dict[str, tuple[datetime, list[str]]] = {}
        self._api_unavailable = not bool(api_key.strip())

    async def collect(self, products: list[Product]) -> list[CommentIn]:
        found: list[CommentIn] = []
        try:
            for product in products:
                for video_id in await self._video_ids(product):
                    found.extend(await self._comments(video_id, product.id))
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning("YouTube collector gagal sementara: %s", exc)
        return found

    async def _video_ids(self, product: Product) -> list[str]:
        now = datetime.now(timezone.utc)
        cached = self._video_cache.get(product.id)
        if cached and cached[0] > now:
            return cached[1]
        query = product.keywords[0] if product.keywords else product.name
        if self._api_unavailable:
            video_ids = await self._public_video_ids(query)
            self._video_cache[product.id] = (now + self.refresh_delta, video_ids)
            return video_ids

        response = await self._client.get(
            f"{API_ROOT}/search",
            params={
                "key": self.api_key,
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "date",
                "regionCode": "ID",
                "relevanceLanguage": "id",
                "maxResults": self.videos_per_product,
            },
        )
        if response.status_code in {400, 403}:
            self._api_unavailable = True
            logger.warning(
                "YouTube Data API tidak tersedia (%s); memakai fallback halaman publik",
                response.status_code,
            )
            video_ids = await self._public_video_ids(query)
            self._video_cache[product.id] = (now + self.refresh_delta, video_ids)
            return video_ids
        response.raise_for_status()
        video_ids = [
            str(item["id"]["videoId"])
            for item in response.json().get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        self._video_cache[product.id] = (now + self.refresh_delta, video_ids)
        return video_ids

    async def _comments(self, video_id: str, product_id: str) -> list[CommentIn]:
        if self._api_unavailable:
            return await self._public_comments(video_id, product_id)

        response = await self._client.get(
            f"{API_ROOT}/commentThreads",
            params={
                "key": self.api_key,
                "part": "snippet",
                "videoId": video_id,
                "maxResults": 50,
                "order": "time",
                "textFormat": "plainText",
            },
        )
        if response.status_code == 403 and self._comments_disabled(response):
            logger.info("Komentar video %s dinonaktifkan; dilewati", video_id)
            return []
        if response.status_code in {400, 403}:
            self._api_unavailable = True
            logger.warning(
                "YouTube Data API komentar tidak tersedia (%s); memakai fallback halaman publik",
                response.status_code,
            )
            return await self._public_comments(video_id, product_id)
        response.raise_for_status()
        comments: list[CommentIn] = []
        for item in response.json().get("items", []):
            mapped = self._map_comment(item, video_id, product_id)
            if mapped is not None:
                comments.append(mapped)
        return comments

    async def _public_video_ids(self, query: str) -> list[str]:
        response = await self._client.get(
            f"{YOUTUBE_ROOT}/results?search_query={quote_plus(query)}&hl=id&gl=ID",
            headers=self._web_headers(),
        )
        response.raise_for_status()
        data = self._extract_initial_data(response.text)
        video_ids: list[str] = []
        for node in self._walk(data):
            renderer = node.get("videoRenderer")
            video_id = renderer.get("videoId") if isinstance(renderer, dict) else None
            if video_id and video_id not in video_ids:
                video_ids.append(str(video_id))
            if len(video_ids) >= self.videos_per_product:
                break
        return video_ids

    async def _public_comments(
        self, video_id: str, product_id: str
    ) -> list[CommentIn]:
        response = await self._client.get(
            f"{YOUTUBE_ROOT}/watch",
            params={"v": video_id, "hl": "id", "gl": "ID"},
            headers=self._web_headers(),
        )
        response.raise_for_status()
        html = response.text
        data = self._extract_initial_data(html)
        panel = next(
            (
                node["engagementPanelSectionListRenderer"]
                for node in self._walk(data)
                if isinstance(node.get("engagementPanelSectionListRenderer"), dict)
                and node["engagementPanelSectionListRenderer"].get("panelIdentifier")
                == "engagement-panel-comments-section"
            ),
            None,
        )
        if panel is None:
            logger.info("Panel komentar video %s tidak tersedia; dilewati", video_id)
            return []

        content = panel.get("content") or {}
        continuation = next(
            (
                node["continuationCommand"]["token"]
                for node in self._walk(content)
                if isinstance(node.get("continuationCommand"), dict)
                and node["continuationCommand"].get("token")
            ),
            None,
        )
        api_key = self._html_config(html, "INNERTUBE_API_KEY")
        client_version = self._html_config(
            html, "INNERTUBE_CONTEXT_CLIENT_VERSION"
        )
        if not continuation or not api_key or not client_version:
            logger.info("Token komentar video %s tidak tersedia; dilewati", video_id)
            return []

        comments_response = await self._client.post(
            f"{YOUTUBE_ROOT}/youtubei/v1/next",
            params={"key": api_key, "prettyPrint": "false"},
            headers={
                **self._web_headers(),
                "Content-Type": "application/json",
                "Origin": YOUTUBE_ROOT,
                "X-YouTube-Client-Name": "1",
                "X-YouTube-Client-Version": client_version,
            },
            json={
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": client_version,
                        "hl": "id",
                        "gl": "ID",
                    }
                },
                "continuation": continuation,
            },
        )
        comments_response.raise_for_status()
        mapped: dict[str, CommentIn] = {}
        for node in self._walk(comments_response.json()):
            payload = node.get("commentEntityPayload")
            comment = self._map_public_comment(payload, video_id, product_id)
            if comment is not None:
                mapped[comment.id] = comment
        return list(mapped.values())

    @staticmethod
    def _web_headers() -> dict[str, str]:
        return {
            "User-Agent": WEB_USER_AGENT,
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        }

    @staticmethod
    def _extract_initial_data(html: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        for marker in ("var ytInitialData = ", "window['ytInitialData'] = ", "ytInitialData = "):
            index = html.find(marker)
            if index < 0:
                continue
            payload = html[index + len(marker) :].lstrip()
            parsed, _ = decoder.raw_decode(payload)
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("ytInitialData tidak ditemukan")

    @classmethod
    def _walk(cls, value: Any):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from cls._walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._walk(child)

    @staticmethod
    def _html_config(html: str, name: str) -> str | None:
        match = re.search(rf'"{re.escape(name)}"\s*:\s*"([^"]+)"', html)
        return match.group(1) if match else None

    @classmethod
    def _map_public_comment(
        cls, payload: Any, video_id: str, product_id: str
    ) -> CommentIn | None:
        if not isinstance(payload, dict):
            return None
        try:
            properties = payload["properties"]
            comment_id = str(properties["commentId"])
            text = str(properties["content"]["content"]).strip()
            if not text:
                return None
            author = payload.get("author") or {}
            author_id = author.get("channelId") or author.get("displayName")
            return CommentIn(
                id=f"yt_{comment_id}",
                source="youtube",
                product_id=product_id,
                text=text,
                url=f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
                author_hash=hash_author(author_id),
                created_at=cls._relative_datetime(properties.get("publishedTime")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Komentar publik YouTube tidak valid dilewati: %s", exc)
            return None

    @staticmethod
    def _relative_datetime(value: Any) -> datetime:
        now = datetime.now(timezone.utc)
        text = str(value or "").lower()
        match = re.search(
            r"(\d+)\s+(detik|second|seconds|menit|minute|minutes|jam|hour|hours|"
            r"hari|day|days|minggu|week|weeks|bulan|month|months|tahun|year|years)",
            text,
        )
        if not match:
            return now
        amount = int(match.group(1))
        unit = match.group(2)
        seconds = {
            "detik": 1,
            "second": 1,
            "seconds": 1,
            "menit": 60,
            "minute": 60,
            "minutes": 60,
            "jam": 3600,
            "hour": 3600,
            "hours": 3600,
            "hari": 86400,
            "day": 86400,
            "days": 86400,
            "minggu": 604800,
            "week": 604800,
            "weeks": 604800,
            "bulan": 2592000,
            "month": 2592000,
            "months": 2592000,
            "tahun": 31536000,
            "year": 31536000,
            "years": 31536000,
        }[unit]
        return now - timedelta(seconds=amount * seconds)

    @staticmethod
    def _comments_disabled(response: httpx.Response) -> bool:
        try:
            errors = response.json().get("error", {}).get("errors", [])
            return any(error.get("reason") == "commentsDisabled" for error in errors)
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def _map_comment(
        item: dict[str, Any], video_id: str, product_id: str
    ) -> CommentIn | None:
        try:
            top_level = item["snippet"]["topLevelComment"]
            snippet = top_level["snippet"]
            comment_id = str(top_level.get("id") or item["id"])
            channel = snippet.get("authorChannelId") or {}
            author = channel.get("value") or snippet.get("authorDisplayName")
            return CommentIn(
                id=f"yt_{item['id']}",
                source="youtube",
                product_id=product_id,
                text=snippet["textDisplay"],
                url=(
                    f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"
                ),
                author_hash=hash_author(author),
                created_at=snippet["publishedAt"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Komentar YouTube tidak valid dilewati: %s", exc)
            return None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
