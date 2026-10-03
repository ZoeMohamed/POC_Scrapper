"""Shared fixtures for API tests with isolated SQLite storage."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import CommentIn, Sentiment, SentimentResult, SourceName

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        ai_mode="mock",
        sources="replay",
        database_path=tmp_path / "test.db",
        products_path=PROJECT_ROOT / "config" / "products.json",
        seed_comments_path=PROJECT_ROOT / "tests" / "fixtures" / "replay_comments.csv",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, start_background=False)) as test_client:
        yield test_client


@pytest.fixture
def seed_comment(client: TestClient) -> Callable[..., None]:
    """Insert a comment and optionally mark it analyzed on the app event loop."""
    database = client.app.state.database
    assert client.portal is not None

    def seed(
        comment_id: str,
        text: str,
        *,
        product_id: str = "kopi-aren",
        source: SourceName = "replay",
        sentiment: Sentiment | None = None,
        score: float = 0.0,
        topics: list[str] | None = None,
        created_at: datetime | None = None,
    ) -> None:
        item = CommentIn(
            id=comment_id,
            source=source,
            product_id=product_id,
            text=text,
            created_at=created_at or datetime.now(timezone.utc),
        )
        inserted = client.portal.call(database.insert_comment, item)
        assert inserted is True
        if sentiment is not None:
            result = SentimentResult(
                id=comment_id,
                sentiment=sentiment,
                score=score,
                topics=topics or [],
            )
            client.portal.call(database.update_analysis, result, "mock")

    return seed
