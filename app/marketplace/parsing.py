"""Normalize varied Shopee Actor rows and keep only product-relevant results."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.models import Topic
from app.nlp.preprocess import normalize


@dataclass(frozen=True)
class MarketplaceProduct:
    product_id: str
    title: str
    description: str
    url: str | None
    shop_name: str | None
    category: str | None
    price: float | None
    original_price: float | None
    rating: float | None
    rating_count: int | None
    sold_count: int | None
    stock: int | None
    image_url: str | None
    query: str
    mentions_product: bool


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _number(value: Any, *, integer: bool = False) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        raw = _text(value).casefold().replace("rp", "").replace("idr", "").strip()
        multiplier = 1
        if raw.endswith("jt"):
            multiplier, raw = 1_000_000, raw[:-2]
        elif raw.endswith(("rb", "k")):
            multiplier, raw = 1_000, raw[:-2] if raw.endswith("rb") else raw[:-1]
        elif raw.endswith("m"):
            multiplier, raw = 1_000_000, raw[:-1]
        raw = re.sub(r"[^0-9.,-]", "", raw).replace(".", "").replace(",", ".")
        try:
            result = float(raw) * multiplier
        except ValueError:
            return None
    return max(0, int(result)) if integer else max(0.0, result)


def _first(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _mentions(text: str, topic: Topic) -> bool:
    haystack = normalize(text)
    signals = [topic.name, *topic.keywords, *topic.product_terms]
    excludes = [normalize(value) for value in topic.exclude_terms if normalize(value)]
    return any(normalize(signal) and normalize(signal) in haystack for signal in signals) and not any(value in haystack for value in excludes)


def parse_shopee_items(items: list[dict[str, Any]], topic: Topic, *, query: str) -> list[MarketplaceProduct]:
    output: list[MarketplaceProduct] = []
    for item in items:
        title = _text(_first(item, "title", "name", "productName", "product_name", "itemName"))
        description = _text(_first(item, "description", "desc", "productDescription"))
        url = _text(_first(item, "url", "productUrl", "product_url", "itemUrl", "link")) or None
        haystack = " ".join((title, description, _text(_first(item, "category", "categoryName"))))
        if not title or not _mentions(haystack, topic):
            continue
        raw_id = _text(_first(item, "id", "itemId", "item_id", "productId", "product_id"))
        product_id = raw_id or (hashlib.sha1((url or title).encode("utf-8")).hexdigest()[:24])
        shop = _first(item, "shopName", "shop_name", "sellerName", "shop", "seller")
        shop_name = _text(shop.get("name") if isinstance(shop, dict) else shop) or None
        output.append(MarketplaceProduct(
            product_id=product_id, title=title, description=description, url=url,
            shop_name=shop_name, category=_text(_first(item, "category", "categoryName")) or None,
            price=_number(_first(item, "price", "priceMin", "price_min")),
            original_price=_number(_first(item, "originalPrice", "original_price", "priceMax", "price_max")),
            rating=_number(_first(item, "rating", "ratingStar", "rating_star")),
            rating_count=_number(_first(item, "ratingCount", "rating_count", "reviewCount", "review_count"), integer=True),
            sold_count=_number(_first(item, "sold", "soldCount", "sold_count", "historicalSold"), integer=True),
            stock=_number(_first(item, "stock", "stockCount"), integer=True),
            image_url=_text(_first(item, "image", "imageUrl", "image_url", "thumbnail")) or None,
            query=query, mentions_product=True,
        ))
    return output
