"""Adapter penyimpanan/event agar loop analyzer tetap kecil dan mudah diuji."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any

from .base import SentimentResult


def setting(settings: Any, name: str, default: Any) -> Any:
    return getattr(settings, name, getattr(settings, name.upper(), default))


async def maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def field(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def as_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


class WorkerIO:
    db: Any
    broker: Any
    _last_status: tuple[Any, ...] | None

    async def _fetch_pending(self, limit: int) -> list[Any]:
        func = self._db_method("get_pending_comments", "fetch_pending_comments", "fetch_pending")
        try:
            return list(await maybe_await(func(limit=limit, max_attempts=5)))
        except TypeError:
            return list(await maybe_await(func(limit)))

    async def _count_pending(self, default: int) -> int:
        func = self._db_method(
            "count_pending_comments", "get_pending_count", "count_pending", required=False
        )
        return int(await maybe_await(func())) if func else default

    async def _increment_attempts(self, ids: list[str]) -> None:
        if not ids:
            return
        func = self._db_method(
            "increment_comment_attempts", "increment_attempts", required=False
        )
        if func:
            try:
                await maybe_await(func(ids))
            except TypeError:
                for comment_id in ids:
                    await maybe_await(func(comment_id))

    async def _save_result(self, result: SentimentResult, analyzer: str) -> Any:
        func = self._db_method("update_comment_analysis", "update_analysis")
        kwargs = {
            "comment_id": result.id, "sentiment": result.sentiment,
            "score": result.score, "topics": result.topics, "analyzer": analyzer,
        }
        try:
            return await maybe_await(func(**kwargs))
        except TypeError:
            try:
                return await maybe_await(func(result, analyzer))
            except TypeError:
                return await maybe_await(func(
                    result.id, result.sentiment, result.score, result.topics, analyzer
                ))

    def _db_method(self, *names: str, required: bool = True) -> Any:
        for name in names:
            func = getattr(self.db, name, None)
            if func:
                return func
        if required:
            raise AttributeError(f"DB belum menyediakan fungsi: {' / '.join(names)}")
        return None

    @staticmethod
    def _result_payload(result: SentimentResult, analyzer: str) -> dict[str, Any]:
        return {
            "id": result.id, "status": "analyzed", "sentiment": result.sentiment,
            "score": result.score, "topics": result.topics, "analyzer": analyzer,
        }

    async def _publish(self, event: str, data: Any) -> None:
        if self.broker is not None:
            await maybe_await(self.broker.publish(event, data))

    async def _publish_status_if_changed(self) -> None:
        snapshot = self.state  # type: ignore[attr-defined]
        fingerprint = tuple(snapshot.items())
        if fingerprint != self._last_status:
            self._last_status = fingerprint
            await self._publish("analyzer_status", snapshot)
