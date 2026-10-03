from __future__ import annotations

from fastapi.testclient import TestClient


def test_v3_topics_health_and_usage(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["yt_comments_enabled"] is False
    assert health["youtube_mode"] == "public"
    assert health["maps_configured"] is False
    assert health["database_backend"] == "sqlite"
    assert set(client.get("/api/usage").json()) == {"youtube", "maps"}

    topics = client.get("/api/topics").json()["items"]
    assert {item["name"] for item in topics} >= {"Cappuccino Cincau", "Kopi Susu Gula Aren", "Seblak"}

    suggestion = client.post("/api/topics/suggest", json={"name": "Keripik Pisang"}).json()
    response = client.post("/api/topics", json={"name": "Keripik Pisang", "keywords": suggestion["keywords"], "product_terms": suggestion["product_terms"], "exclude_terms": [], "category": suggestion["category"], "cities": ["Bandung"]})
    assert response.status_code == 201
    assert response.json()["id"] == "keripik-pisang"
    trend = client.get("/api/trend", params={"topic_id": "keripik-pisang"})
    assert trend.status_code == 200
    assert trend.json()["videos_tracked"] == 0
