"""Contract tests for the dashboard HTTP API."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.models import CommentIn


def test_health_reports_offline_mock_mode(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["sources_active"] == ["replay"]
    assert payload["analyzer"]["ai_mode"] == "mock"
    assert payload["analyzer"]["active_analyzer"] == "mock"


def test_feed_filters_search_and_cursor(
    client: TestClient, seed_comment: Callable[..., None]
) -> None:
    seed_comment("rp_old", "kopi aren biasa saja")
    seed_comment(
        "yt_positive", "Kopi aren enak dan kemasan premium",
        source="youtube", sentiment="positif", score=0.8, topics=["rasa", "kemasan"],
    )
    seed_comment(
        "rp_negative", "Harga terlalu mahal dan pengiriman lama",
        sentiment="negatif", score=-0.8, topics=["harga", "pengiriman"],
    )

    filtered = client.get(
        "/api/feed",
        params={
            "product_id": "kopi-aren", "sentiment": "positif",
            "source": "youtube", "q": "premium",
        },
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == ["yt_positive"]

    first_page = client.get("/api/feed", params={"limit": 2}).json()
    assert len(first_page["items"]) == 2
    assert first_page["next_before"] is not None

    second_page = client.get(
        "/api/feed", params={"limit": 2, "before": first_page["next_before"]}
    ).json()
    first_ids = {item["id"] for item in first_page["items"]}
    second_ids = {item["id"] for item in second_page["items"]}
    assert second_ids == {"rp_old"}
    assert first_ids.isdisjoint(second_ids)


def test_feed_orders_by_created_at_and_pages_with_stable_cursor(
    client: TestClient, seed_comment: Callable[..., None]
) -> None:
    now = datetime.now(timezone.utc)
    rows = [
        ("rp_middle", now - timedelta(hours=2)),
        ("rp_oldest", now - timedelta(days=2)),
        ("rp_same_a", now - timedelta(hours=1)),
        ("rp_newest", now),
        ("rp_same_z", now - timedelta(hours=1)),
    ]
    for comment_id, created_at in rows:
        seed_comment(comment_id, comment_id, created_at=created_at)

    found: list[str] = []
    before: str | None = None
    while True:
        params = {"limit": 2, "window": "all"}
        if before:
            params["before"] = before
        payload = client.get("/api/feed", params=params).json()
        found.extend(item["id"] for item in payload["items"])
        before = payload["next_before"]
        if before is None:
            break

    assert found == [
        "rp_newest", "rp_same_z", "rp_same_a", "rp_middle", "rp_oldest"
    ]
    assert len(found) == len(set(found))


def test_feed_default_window_is_30_days_and_rejects_bad_cursor(
    client: TestClient, seed_comment: Callable[..., None]
) -> None:
    now = datetime.now(timezone.utc)
    seed_comment("rp_recent", "masih baru", created_at=now - timedelta(days=29))
    seed_comment("rp_older", "lebih dari sebulan", created_at=now - timedelta(days=31))

    default_ids = [item["id"] for item in client.get("/api/feed").json()["items"]]
    all_ids = [
        item["id"]
        for item in client.get("/api/feed", params={"window": "all"}).json()["items"]
    ]

    assert default_ids == ["rp_recent"]
    assert all_ids == ["rp_recent", "rp_older"]
    assert client.get("/api/feed", params={"before": "invalid"}).status_code == 422


def test_database_rejects_comment_older_than_limit(client: TestClient) -> None:
    assert client.portal is not None
    old_comment = CommentIn(
        id="rp_too_old",
        source="replay",
        product_id="kopi-aren",
        text="komentar lama",
        created_at=datetime.now(timezone.utc) - timedelta(days=181),
    )

    inserted = client.portal.call(client.app.state.database.insert_comment, old_comment)

    assert inserted is False
    response = client.get("/api/feed", params={"window": "all"})
    assert response.json()["items"] == []


def test_stats_respect_window_product_and_keyword_exclusions(
    client: TestClient, seed_comment: Callable[..., None]
) -> None:
    now = datetime.now(timezone.utc)
    seed_comment(
        "rp_recent_positive", "kopi aren rasanya enak harga murah",
        sentiment="positif", score=0.9, topics=["rasa", "harga"], created_at=now,
    )
    seed_comment(
        "rp_recent_pending", "kopi aren kemasan baru",
        created_at=now - timedelta(minutes=10),
    )
    seed_comment(
        "rp_old_negative", "kopi aren mahal dan mengecewakan",
        sentiment="negatif", score=-0.8, topics=["harga"],
        created_at=now - timedelta(hours=2),
    )
    seed_comment(
        "rp_other_product", "batik tulis bagus",
        product_id="batik-tulis", sentiment="positif", score=0.7,
        created_at=now,
    )

    response = client.get(
        "/api/stats", params={"product_id": "kopi-aren", "window": "1h"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["sentiment"] == {
        "positif": 1, "negatif": 0, "netral": 0, "pending": 1,
    }
    assert payload["top_topics"][:2] == [
        {"topic": "rasa", "count": 1}, {"topic": "harga", "count": 1},
    ]
    keyword_words = {item["word"] for item in payload["top_keywords"]}
    assert "kopi" not in keyword_words
    assert "aren" not in keyword_words
    assert "harga" in keyword_words


def test_summary_uses_five_minute_cache_in_mock_mode(
    client: TestClient, seed_comment: Callable[..., None]
) -> None:
    seed_comment(
        "rp_summary_positive", "Rasa enak dan harga bersahabat",
        sentiment="positif", score=0.8, topics=["rasa", "harga"],
    )
    first = client.get("/api/summary", params={"product_id": "kopi-aren"})
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["analyzer"] == "template"
    assert first_payload["praises"]

    seed_comment(
        "rp_summary_negative", "Pengiriman lama dan kemasan rusak",
        sentiment="negatif", score=-0.9, topics=["pengiriman", "kemasan"],
    )
    second = client.get("/api/summary", params={"product_id": "kopi-aren"})
    assert second.status_code == 200
    assert second.json() == first_payload
