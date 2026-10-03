"""Contract and privacy tests for the local marketplace review bridge."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "marketplace": "tokopedia",
        "product_id": "kopi-aren",
        "product_url": "https://www.tokopedia.com/umkm/kopi-aren?source=tracking#review",
        "reviews": [
            {
                "external_id": "review-42",
                "text": "Rasa kopinya enak dan kemasannya sangat rapi.",
                "rating": 5,
            }
        ],
    }
    payload.update(updates)
    return payload


def test_marketplace_batch_is_live_deduplicated_and_sanitized(
    client: TestClient,
) -> None:
    first = client.post("/api/ingest/marketplace", json=_payload())

    assert first.status_code == 202
    assert first.json()["accepted"] == 1
    assert first.json()["duplicates"] == 0
    assert first.json()["comment_ids"][0].startswith("tp_")

    duplicate = client.post("/api/ingest/marketplace", json=_payload())
    assert duplicate.status_code == 202
    assert duplicate.json()["accepted"] == 0
    assert duplicate.json()["duplicates"] == 1

    feed = client.get(
        "/api/feed", params={"source": "tokopedia", "product_id": "kopi-aren"}
    ).json()["items"]
    assert len(feed) == 1
    assert feed[0]["source"] == "tokopedia"
    assert feed[0]["url"] == "https://www.tokopedia.com/umkm/kopi-aren"
    assert feed[0]["author_hash"] is None
    assert feed[0]["status"] == "pending"


def test_marketplace_ingest_validates_product_host_and_privacy(
    client: TestClient,
) -> None:
    unknown_product = client.post(
        "/api/ingest/marketplace", json=_payload(product_id="produk-tidak-ada")
    )
    assert unknown_product.status_code == 422

    spoofed_host = client.post(
        "/api/ingest/marketplace",
        json=_payload(product_url="https://tokopedia.com.example.test/produk"),
    )
    assert spoofed_host.status_code == 422

    credential_url = client.post(
        "/api/ingest/marketplace",
        json=_payload(product_url="https://tracking@tokopedia.com/produk"),
    )
    assert credential_url.status_code == 422

    payload = _payload()
    payload["reviews"] = [
        {
            "text": "Ulasan valid tetapi nama akun tidak boleh diterima.",
            "author_name": "nama-pelanggan",
        }
    ]
    raw_author = client.post("/api/ingest/marketplace", json=payload)
    assert raw_author.status_code == 422


def test_marketplace_ingest_supports_tiktok_shop(client: TestClient) -> None:
    response = client.post(
        "/api/ingest/marketplace",
        json=_payload(
            marketplace="tiktokshop",
            product_url="https://shop.tiktok.com/view/product/123?region=ID",
            reviews=[{"text": "Bahannya bagus, ukuran pas, pengiriman cepat."}],
        ),
    )

    assert response.status_code == 202
    assert response.json()["accepted"] == 1
    assert response.json()["comment_ids"][0].startswith("ts_")


def test_marketplace_ingest_supports_shopee(client: TestClient) -> None:
    response = client.post(
        "/api/ingest/marketplace",
        json=_payload(
            marketplace="shopee",
            product_url="https://shopee.co.id/produk-umkm-i.123.456?sp_atk=tracking",
            reviews=[{"text": "Produk lokal bagus, sesuai foto dan cepat sampai."}],
        ),
    )

    assert response.status_code == 202
    assert response.json()["accepted"] == 1
    assert response.json()["comment_ids"][0].startswith("sp_")


def test_configured_ingest_token_is_required(
    settings: Settings, tmp_path: Path
) -> None:
    protected = settings.model_copy(
        update={
            "database_path": tmp_path / "protected.db",
            "marketplace_ingest_token": "token-rahasia-test",
        }
    )
    with TestClient(create_app(protected, start_background=False)) as client:
        missing = client.post("/api/ingest/marketplace", json=_payload())
        wrong = client.post(
            "/api/ingest/marketplace",
            headers={"X-Ingest-Token": "salah"},
            json=_payload(),
        )
        accepted = client.post(
            "/api/ingest/marketplace",
            headers={"X-Ingest-Token": "token-rahasia-test"},
            json=_payload(),
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert accepted.status_code == 202


def test_chrome_extension_origin_passes_cors_preflight(client: TestClient) -> None:
    origin = f"chrome-extension://{'a' * 32}"
    response = client.options(
        "/api/ingest/marketplace",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-ingest-token",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
