"""Cached AI summary endpoint with a deterministic local fallback."""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import Settings
from app.analyzer.gemini_pool import GeminiClientPool
from app.db import Database
from app.models import Comment, Summary


class RateLimiter(Protocol):
    async def acquire(self) -> None: ...


class GeminiSummaryPayload(BaseModel):
    summary: str
    praises: list[str] = Field(default_factory=list, max_length=3)
    complaints: list[str] = Field(default_factory=list, max_length=3)
    innovation_ideas: list[str] = Field(default_factory=list, max_length=3)


SummaryGenerator = Callable[[list[Comment]], Awaitable[GeminiSummaryPayload | dict[str, Any]]]


def _worker_healthy(worker: Any | None) -> bool:
    if worker is None:
        return True
    state = getattr(worker, "state", worker)
    if callable(state):
        state = state()
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    return not isinstance(state, dict) or bool(state.get("gemini_healthy", True))


def _template_summary(comments: list[Comment]) -> Summary:
    counts = Counter(comment.sentiment for comment in comments if comment.sentiment)
    topics = Counter(topic for comment in comments for topic in comment.topics)
    total = max(1, sum(counts.values()))
    positive = round(counts["positif"] * 100 / total)
    negative = round(counts["negatif"] * 100 / total)
    leading = ", ".join(topic for topic, _ in topics.most_common(3)) or "belum ada topik dominan"
    if comments:
        text = (
            f"Dari {len(comments)} opini terbaru, {positive}% bernada positif dan "
            f"{negative}% bernada negatif. Topik yang paling sering dibahas: {leading}."
        )
    else:
        text = "Belum cukup opini yang telah dianalisis untuk membuat ringkasan."
    praised = Counter(t for c in comments if c.sentiment == "positif" for t in c.topics)
    complained = Counter(t for c in comments if c.sentiment == "negatif" for t in c.topics)
    complaints = [f"Keluhan terkait {topic}" for topic, _ in complained.most_common(3)]
    praises = [f"Apresiasi pada {topic}" for topic, _ in praised.most_common(3)]
    ideas = [f"Evaluasi dan tingkatkan aspek {topic}" for topic, _ in complained.most_common(3)]
    if not ideas and comments:
        ideas = ["Pertahankan kualitas dan kumpulkan lebih banyak masukan pelanggan"]
    return Summary(
        summary=text, praises=praises, complaints=complaints,
        innovation_ideas=ideas, generated_at=datetime.now(timezone.utc), analyzer="template",
    )


class SummaryService:
    """Own cache/rate-limit state independently from HTTP request handling."""

    def __init__(
        self, database: Database, settings: Settings, *, worker: Any | None = None,
        limiter: RateLimiter | None = None, generator: SummaryGenerator | None = None,
        cache_seconds: float = 300, refresh_seconds: float = 30,
    ) -> None:
        self.database = database
        self.settings = settings
        self.worker = worker
        self.limiter = limiter
        self.generator = generator
        self._gemini_pool = (
            GeminiClientPool(settings.gemini_api_key_values)
            if generator is None and settings.gemini_api_key_values else None
        )
        self.cache_seconds = cache_seconds
        self.refresh_seconds = refresh_seconds
        self._cache: dict[str, tuple[float, Summary]] = {}
        self._last_refresh: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get(self, product_id: str | None, refresh: bool = False) -> Summary:
        key = product_id or "__all__"
        now = time.monotonic()
        cached = self._cache.get(key)
        refresh_allowed = now - self._last_refresh.get(key, float("-inf")) >= self.refresh_seconds
        if cached and ((not refresh and now - cached[0] < self.cache_seconds) or not refresh_allowed):
            return cached[1]
        async with self._lock:
            now = time.monotonic()
            cached = self._cache.get(key)
            refresh_allowed = now - self._last_refresh.get(key, float("-inf")) >= self.refresh_seconds
            if cached and ((not refresh and now - cached[0] < self.cache_seconds) or not refresh_allowed):
                return cached[1]
            comments = await self.database.get_analyzed_recent(product_id, 60)
            result = await self._generate(comments)
            self._cache[key] = (now, result)
            if refresh:
                self._last_refresh[key] = now
            return result

    async def _generate(self, comments: list[Comment]) -> Summary:
        if not comments or self.settings.ai_mode != "gemini" or not _worker_healthy(self.worker):
            return _template_summary(comments)
        try:
            if self.limiter:
                await self.limiter.acquire()
            generator = self.generator or self._gemini_generate
            raw = await generator(comments)
            payload = raw if isinstance(raw, GeminiSummaryPayload) else GeminiSummaryPayload.model_validate(raw)
            return Summary(
                **payload.model_dump(), generated_at=datetime.now(timezone.utc), analyzer="gemini"
            )
        except Exception:
            return _template_summary(comments)

    async def _gemini_generate(self, comments: list[Comment]) -> GeminiSummaryPayload:
        if self._gemini_pool is None:
            raise RuntimeError("GEMINI_API_KEY atau GEMINI_API_KEYS belum diisi")
        from google.genai import types
        compact = [{"s": c.sentiment, "t": c.text, "tp": c.topics} for c in comments]
        prompt = (
            "Ringkas opini produk UMKM berikut dalam Bahasa Indonesia. Berikan 2-3 kalimat, "
            "maksimal 3 pujian, 3 keluhan, dan 3 ide inovasi konkret. Data: "
            + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        )
        response = await self._gemini_pool.generate_content(
            model=self.settings.gemini_model, contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0, response_mime_type="application/json",
                response_schema=GeminiSummaryPayload,
            ),
        )
        if response.parsed:
            return GeminiSummaryPayload.model_validate(response.parsed)
        return GeminiSummaryPayload.model_validate_json(response.text)


def create_summary_router(service: SummaryService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["summary"])

    @router.get("/summary", response_model=Summary)
    async def get_summary(product_id: str | None = None, refresh: bool = False) -> Summary:
        return await service.get(product_id, refresh)

    return router
