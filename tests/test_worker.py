from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.analyzer.base import AnalyzerError, BaseAnalyzer, RateLimitedError, SentimentResult
from app.analyzer.worker import AnalyzerWorker


def _settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "ai_mode": "mock", "batch_size": 2, "batch_max_wait_seconds": 15,
        "max_gemini_failures": 3, "gemini_rpm": 8,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDB:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []
        self.attempted: list[str] = []

    async def increment_attempts(self, ids: list[str]) -> None:
        self.attempted.extend(ids)

    async def update_comment_analysis(self, **values: Any) -> dict[str, Any]:
        self.saved.append(values)
        return values


class FakeBroker:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    async def publish(self, name: str, data: Any) -> None:
        self.events.append((name, data))


class NoWaitLimiter:
    async def acquire(self) -> None:
        return None


class FailingGemini(BaseAnalyzer):
    name = "gemini"

    def __init__(self, rate_limited: bool = False) -> None:
        self.calls = 0
        self.rate_limited = rate_limited

    async def analyze(self, items: list[tuple[str, str]]) -> list[SentimentResult]:
        self.calls += 1
        if self.rate_limited:
            raise RateLimitedError("429")
        raise AnalyzerError("API key salah")


def _row(comment_id: str = "rp_1", age: float = 0) -> dict[str, Any]:
    return {
        "id": comment_id,
        "text": "bagus",
        "collected_at": datetime.now(timezone.utc) - timedelta(seconds=age),
    }


def test_batch_triggers_by_size_or_oldest_wait_time() -> None:
    worker = AnalyzerWorker(_settings(), FakeDB(), FakeBroker())
    assert worker.should_process([_row("1"), _row("2")])
    assert worker.should_process([_row(age=16)])
    assert not worker.should_process([_row(age=2)])


@pytest.mark.asyncio
async def test_worker_falls_back_after_configured_failures() -> None:
    gemini, database = FailingGemini(), FakeDB()
    worker = AnalyzerWorker(
        _settings(ai_mode="gemini"), database, FakeBroker(),
        analyzer=gemini, limiter=NoWaitLimiter(),  # type: ignore[arg-type]
    )
    assert await worker.process_batch([_row()]) == []
    assert await worker.process_batch([_row()]) == []
    third = await worker.process_batch([_row()])
    assert third[0].sentiment == "positif"
    assert worker.state["active_analyzer"] == "lexicon"
    assert worker.state["gemini_healthy"] is False
    assert gemini.calls == 3
    assert database.saved[0]["analyzer"] == "lexicon"


@pytest.mark.asyncio
async def test_rate_limit_sets_cooldown_and_next_batch_uses_fallback() -> None:
    gemini = FailingGemini(rate_limited=True)
    worker = AnalyzerWorker(
        _settings(ai_mode="gemini"), FakeDB(), FakeBroker(),
        analyzer=gemini, limiter=NoWaitLimiter(),  # type: ignore[arg-type]
    )
    assert await worker.process_batch([_row()]) == []
    assert worker.state["cooldown_until"] is not None
    result = await worker.process_batch([_row("rp_2")])
    assert result[0].sentiment == "positif"
    assert worker.state["active_analyzer"] == "lexicon"
    assert gemini.calls == 1


@pytest.mark.asyncio
async def test_social_text_rate_limit_falls_back_in_same_request() -> None:
    gemini = FailingGemini(rate_limited=True)
    worker = AnalyzerWorker(
        _settings(ai_mode="gemini"), FakeDB(), FakeBroker(),
        analyzer=gemini, limiter=NoWaitLimiter(),  # type: ignore[arg-type]
    )
    result = await worker.analyze_texts([("facebook:post-1", "rasanya enak")])
    assert result[0].sentiment == "positif"
    assert worker.state["active_analyzer"] == "lexicon"
    assert worker.state["gemini_healthy"] is False
    assert gemini.calls == 1
