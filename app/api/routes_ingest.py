"""Push ingestion for reviews captured from a user's marketplace page."""

from __future__ import annotations

import hashlib
import ipaddress
import secrets
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings
from app.db import Database
from app.events import EventBroker
from app.models import CommentIn
from app.products import ProductCatalog

MarketplaceName = Literal["tokopedia", "shopee", "tiktokshop"]


class MarketplaceReview(BaseModel):
    """Minimal review payload; account names are intentionally not accepted."""

    model_config = ConfigDict(extra="forbid")

    external_id: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=5000)
    rating: float | None = Field(default=None, ge=1, le=5)
    created_at: datetime | None = None

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("teks ulasan tidak boleh kosong")
        return cleaned

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class MarketplaceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marketplace: MarketplaceName
    product_id: str = Field(min_length=1, max_length=100)
    product_url: str = Field(min_length=8, max_length=2000)
    reviews: list[MarketplaceReview] = Field(min_length=1, max_length=100)


def _allowed_host(marketplace: MarketplaceName, hostname: str) -> bool:
    expected_by_marketplace = {
        "tokopedia": ("tokopedia.com",),
        "shopee": ("shopee.co.id",),
        "tiktokshop": ("tiktok.com", "tiktokshop.com", "tiktokglobalshop.com"),
    }
    expected = expected_by_marketplace[marketplace]
    host = hostname.rstrip(".").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in expected)


def _sanitize_product_url(marketplace: MarketplaceName, raw_url: str) -> str:
    try:
        parsed = urlsplit(raw_url)
        hostname = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or not _allowed_host(marketplace, hostname)
        ):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="URL produk tidak cocok dengan marketplace yang dipilih",
        ) from exc
    # Tracking parameters and fragments are not useful to the dashboard.
    return urlunsplit((parsed.scheme, hostname.lower(), parsed.path or "/", "", ""))


def _is_loopback(host: str) -> bool:
    if host == "testclient":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _authorize(request: Request, supplied: str | None, configured: str) -> None:
    if configured:
        if not supplied or not secrets.compare_digest(supplied, configured):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token ingest tidak valid",
            )
        return
    client_host = request.client.host if request.client else ""
    if not _is_loopback(client_host):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tanpa token, ingest hanya tersedia dari komputer lokal",
        )


def _comment_id(
    marketplace: MarketplaceName,
    product_id: str,
    product_url: str,
    review: MarketplaceReview,
) -> str:
    identity = review.external_id or "|".join(
        (review.text, str(review.rating or ""))
    )
    digest = hashlib.sha256(
        f"{marketplace}|{product_id}|{product_url}|{identity}".encode("utf-8")
    ).hexdigest()[:24]
    prefix = {"tokopedia": "tp", "shopee": "sp", "tiktokshop": "ts"}[marketplace]
    return f"{prefix}_{digest}"


def create_ingest_router(
    database: Database,
    products: ProductCatalog,
    broker: EventBroker,
    settings: Settings,
) -> APIRouter:
    router = APIRouter(prefix="/api/ingest", tags=["ingest"])

    @router.post("/marketplace", status_code=status.HTTP_202_ACCEPTED)
    async def ingest_marketplace(
        batch: MarketplaceBatch,
        request: Request,
        x_ingest_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        _authorize(request, x_ingest_token, settings.marketplace_ingest_token)
        if products.get(batch.product_id) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="product_id tidak terdaftar di config/products.json",
            )

        product_url = _sanitize_product_url(batch.marketplace, batch.product_url)
        received_at = datetime.now(timezone.utc)
        comments = [
            CommentIn(
                id=_comment_id(
                    batch.marketplace, batch.product_id, product_url, review
                ),
                source=batch.marketplace,
                product_id=batch.product_id,
                text=review.text,
                url=product_url,
                # Usernames are not collected by the extension or persisted.
                author_hash=None,
                created_at=review.created_at or received_at,
            )
            for review in batch.reviews
        ]
        inserted = await database.insert_comments(
            comments, max_comment_chars=settings.max_comment_chars
        )
        for comment in inserted:
            await broker.publish("comment_new", comment)

        return {
            "source": batch.marketplace,
            "received": len(comments),
            "accepted": len(inserted),
            "duplicates": len(comments) - len(inserted),
            "comment_ids": [comment.id for comment in inserted],
        }

    return router
