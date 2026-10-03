"""Aggregate sentiment, keyword, topic, and source statistics."""

from __future__ import annotations

from collections import Counter
from fastapi import APIRouter, Query

from app.db import Database
from app.models import CountItem, Stats, TopicCount
from app.nlp.keywords import top_keywords
from app.products import ProductCatalog

from .windows import Window, since_for_window


async def calculate_stats(
    database: Database, catalog: ProductCatalog, product_id: str | None,
    window: Window, ngram: int,
) -> Stats:
    since = since_for_window(window)
    comments = await database.get_stats_rows(product_id, since)
    sentiment = Counter({"positif": 0, "negatif": 0, "netral": 0, "pending": 0})
    sources: Counter[str] = Counter()
    topics: Counter[str] = Counter()
    for comment in comments:
        sentiment[comment.sentiment or "pending"] += 1
        sources[comment.source] += 1
        topics.update(comment.topics)
    keywords = top_keywords(
        (comment.text for comment in comments),
        exclude=catalog.keyword_exclusions(product_id), n=10, ngram=ngram,
    )
    return Stats(
        product_id=product_id, window=window, total=len(comments),
        sentiment=dict(sentiment),
        top_keywords=[CountItem(word=word, count=count) for word, count in keywords],
        top_topics=[TopicCount(topic=topic, count=count) for topic, count in topics.most_common(10)],
        by_source=dict(sources),
    )


def create_stats_router(
    database: Database,
    catalog: ProductCatalog,
    default_window: Window = "30d",
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["stats"])

    @router.get("/stats", response_model=Stats)
    async def get_stats(
        product_id: str | None = None,
        window: Window = Query(default=default_window),
        ngram: int = Query(default=1, ge=1, le=2),
    ) -> Stats:
        return await calculate_stats(database, catalog, product_id, window, ngram)

    return router
