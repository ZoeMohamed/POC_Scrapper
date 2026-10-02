"""Worker background untuk batching, fallback, dan publikasi hasil."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .base import BaseAnalyzer, RateLimitedError, SentimentResult
from .gemini import GeminiAnalyzer
from .lexicon import LexiconAnalyzer
from .mock import MockAnalyzer
from .rate_limiter import AsyncRateLimiter
from .worker_support import WorkerIO, as_utc, field, setting

logger = logging.getLogger(__name__)


class AnalyzerWorker(WorkerIO):
    """Ambil komentar pending dan analisis tanpa memblokir request HTTP."""

    def __init__(
        self,
        settings: Any,
        db: Any | None = None,
        broker: Any | None = None,
        *,
        analyzer: BaseAnalyzer | None = None,
        fallback_analyzer: BaseAnalyzer | None = None,
        limiter: AsyncRateLimiter | None = None,
        poll_interval: float = 2.0,
    ) -> None:
        if db is None:
            from app import db as db_module
            db = db_module
        self.settings, self.db, self.broker = settings, db, broker
        self.ai_mode = str(setting(settings, "ai_mode", "mock")).lower()
        self.batch_size = int(setting(settings, "batch_size", 25))
        self.max_wait = float(setting(settings, "batch_max_wait_seconds", 15))
        self.max_failures = int(setting(settings, "max_gemini_failures", 3))
        self.poll_interval = poll_interval
        self.fallback = fallback_analyzer or LexiconAnalyzer()
        self.limiter = limiter or AsyncRateLimiter(int(setting(settings, "gemini_rpm", 8)))
        self.gemini_failures = 0
        self.cooldown_until: datetime | None = None
        self.last_error: str | None = None
        self._stop = asyncio.Event()
        self._last_status: tuple[Any, ...] | None = None
        self.analyzer = analyzer or self._build_analyzer()
        self.active_analyzer = self.analyzer.name
        self.gemini_healthy = self.ai_mode != "gemini" or self.analyzer.name == "gemini"
        if self.ai_mode == "gemini" and self.analyzer.name != "gemini":
            self.gemini_failures = self.max_failures
            self.gemini_healthy = False

    def _build_analyzer(self) -> BaseAnalyzer:
        if self.ai_mode == "lexicon":
            return self.fallback
        if self.ai_mode == "gemini":
            try:
                return GeminiAnalyzer(self.settings)
            except (ValueError, RuntimeError) as exc:
                self.last_error = str(exc)
                logger.warning("Gemini tidak tersedia, memakai leksikon: %s", exc)
                return self.fallback
        return MockAnalyzer()

    @property
    def state(self) -> dict[str, Any]:
        return {
            "ai_mode": self.ai_mode,
            "active_analyzer": self.active_analyzer,
            "gemini_healthy": self.gemini_healthy,
            "cooldown_until": self.cooldown_until.isoformat().replace("+00:00", "Z")
            if self.cooldown_until else None,
            "last_error": self.last_error,
            "pending_count": getattr(self, "pending_count", 0),
        }

    def should_process(self, pending: list[Any], now: datetime | None = None) -> bool:
        if not pending:
            return False
        if len(pending) >= self.batch_size:
            return True
        collected_at = field(pending[0], "collected_at")
        if collected_at is None:
            return True
        age = (now or datetime.now(timezone.utc)) - as_utc(collected_at)
        return age.total_seconds() >= self.max_wait

    async def run(self) -> None:
        self._stop.clear()
        while not self._stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Siklus analyzer gagal; worker tetap berjalan")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()

    async def tick(self) -> bool:
        pending = await self._fetch_pending(self.batch_size)
        self.pending_count = await self._count_pending(default=len(pending))
        if not self.should_process(pending):
            return False
        await self.process_batch(pending[:self.batch_size])
        self.pending_count = await self._count_pending(
            default=max(0, self.pending_count - len(pending))
        )
        return True

    async def process_batch(self, batch: list[Any]) -> list[SentimentResult]:
        items = [(str(field(row, "id")), str(field(row, "text", ""))) for row in batch]
        selected = self.analyzer
        failed = False
        if self.ai_mode == "gemini":
            now = datetime.now(timezone.utc)
            if (
                selected.name != "gemini"
                or self.gemini_failures >= self.max_failures
                or (self.cooldown_until and now < self.cooldown_until)
            ):
                selected = self.fallback
            else:
                await self.limiter.acquire()
        try:
            results = await selected.analyze(items)
            if selected.name == "gemini":
                self.gemini_failures = 0
                self.gemini_healthy = True
                self.cooldown_until = None
                self.last_error = None
        except RateLimitedError as exc:
            failed = True
            self._gemini_failed(exc, rate_limited=True)
            results = []
        except Exception as exc:
            failed = True
            if self.ai_mode == "gemini" and selected.name == "gemini":
                self._gemini_failed(exc, rate_limited=False)
            else:
                self.last_error = str(exc)
            results = []

        if failed:
            await self._increment_attempts([comment_id for comment_id, _ in items])
            if self.ai_mode == "gemini" and self.gemini_failures >= self.max_failures:
                selected = self.fallback
                results = await selected.analyze(items)
            else:
                await self._publish_status_if_changed()
                return []

        self.active_analyzer = selected.name
        returned = {result.id for result in results}
        missing = [comment_id for comment_id, _ in items if comment_id not in returned]
        if missing:
            await self._increment_attempts(missing)
        for result in results:
            updated = await self._save_result(result, selected.name)
            await self._publish("comment_updated", updated or self._result_payload(result, selected.name))
        await self._publish_status_if_changed()
        return results

    async def analyze_texts(self, items: list[tuple[str, str]]) -> list[SentimentResult]:
        """Analyze non-comment text (for example social captions) with the same fallback policy."""
        if not items:
            return []
        # Mock mode is useful for legacy comment fixtures, but social trend
        # sentiment must remain meaningful even when no Gemini key is set.
        selected = self.fallback if self.ai_mode == "mock" else self.analyzer
        failed = False
        if self.ai_mode == "gemini":
            now = datetime.now(timezone.utc)
            if (
                selected.name != "gemini"
                or self.gemini_failures >= self.max_failures
                or (self.cooldown_until and now < self.cooldown_until)
            ):
                selected = self.fallback
            else:
                await self.limiter.acquire()
        try:
            results = await selected.analyze(items)
            if selected.name == "gemini":
                self.gemini_failures = 0
                self.gemini_healthy = True
                self.cooldown_until = None
                self.last_error = None
        except RateLimitedError as exc:
            failed = True
            self._gemini_failed(exc, rate_limited=True)
            results = []
        except Exception as exc:
            failed = True
            if self.ai_mode == "gemini" and selected.name == "gemini":
                self._gemini_failed(exc, rate_limited=False)
            else:
                self.last_error = str(exc)
            results = []
        # Social refreshes are request-scoped on Vercel, so a failure counter
        # cannot reliably survive until the next cold start. Fall back in the
        # same bounded request and leave captions analyzed without another
        # Gemini or Apify call.
        if failed and self.ai_mode == "gemini":
            selected = self.fallback
            results = await selected.analyze(items)
        if not failed or results:
            self.active_analyzer = selected.name
        await self._publish_status_if_changed()
        return results

    def _gemini_failed(self, exc: Exception, *, rate_limited: bool) -> None:
        self.gemini_failures += 1
        self.gemini_healthy = False
        self.last_error = str(exc)
        if rate_limited:
            seconds = min(60, 15 * (2 ** (self.gemini_failures - 1)))
            self.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
