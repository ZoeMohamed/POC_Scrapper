"""Normalize the flexible JSON emitted by the Apify Maps Actor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ParsedReview:
    review_id: str
    text: str
    stars: int | None
    author_name: str | None
    author_uri: str | None
    url: str | None
    created_at: datetime


@dataclass(frozen=True)
class ParsedPlace:
    place_id: str
    name: str
    address: str | None
    url: str | None
    primary_type: str | None
    business_status: str | None
    rating: float | None
    user_rating_count: int | None
    reviews: list[ParsedReview] = field(default_factory=list)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _number(value: Any, *, integer: bool = False) -> int | float | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value)) if integer else float(value)
    except (TypeError, ValueError):
        return None


def _date(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = _text(value)
        # Apify may return ISO strings, date-only values, or localized text.
        parsed = None
        if raw:
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed = datetime.strptime(raw[:10], "%Y-%m-%d")
                except ValueError:
                    parsed = None
    if parsed is None:
        parsed = fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _stars(value: Any) -> int | None:
    score = _number(value)
    if score is None:
        return None
    return max(1, min(5, int(round(score))))


def parse_apify_items(items: list[dict[str, Any]], *, now: datetime | None = None) -> list[ParsedPlace]:
    """Parse Actor output while tolerating the common field aliases."""

    collected = now or datetime.now(timezone.utc)
    if collected.tzinfo is None:
        collected = collected.replace(tzinfo=timezone.utc)
    result: list[ParsedPlace] = []
    for item in items:
        place_id = _text(item.get("placeId") or item.get("place_id") or item.get("id"))
        if not place_id:
            continue
        name = _text(item.get("title") or item.get("name")) or "Tempat tanpa nama"
        reviews_raw = item.get("reviews") or item.get("reviewsData") or []
        if isinstance(reviews_raw, dict):
            reviews_raw = [reviews_raw]
        reviews: list[ParsedReview] = []
        for raw in reviews_raw if isinstance(reviews_raw, list) else []:
            if not isinstance(raw, dict):
                continue
            review_id = _text(raw.get("reviewId") or raw.get("review_id") or raw.get("id"))
            text = _text(raw.get("text") or raw.get("reviewText") or raw.get("snippet"))
            if not review_id or not text:
                continue
            reviews.append(
                ParsedReview(
                    review_id=review_id,
                    text=text,
                    stars=_stars(raw.get("stars") if raw.get("stars") is not None else raw.get("rating")),
                    author_name=_text(raw.get("name") or raw.get("reviewerName")) or None,
                    author_uri=_text(raw.get("reviewerUrl") or raw.get("authorUrl")) or None,
                    url=_text(raw.get("reviewUrl") or raw.get("url")) or _text(item.get("url")) or None,
                    created_at=_date(
                        raw.get("publishedAtDate") or raw.get("publishedDate") or raw.get("date"),
                        collected,
                    ),
                )
            )
        result.append(
            ParsedPlace(
                place_id=place_id,
                name=name,
                address=_text(item.get("address") or item.get("street")) or None,
                url=_text(item.get("url") or item.get("googleMapsUrl")) or None,
                primary_type=_text(item.get("categoryName") or item.get("category")) or None,
                business_status=_text(item.get("businessStatus") or item.get("business_status")) or None,
                rating=_number(item.get("totalScore") if item.get("totalScore") is not None else item.get("rating")),
                user_rating_count=_number(
                    item.get("reviewsCount") if item.get("reviewsCount") is not None else item.get("userRatingCount"),
                    integer=True,
                ),
                reviews=reviews,
            )
        )
    return result
