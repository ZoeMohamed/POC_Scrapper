"""Analyzer lokal deterministik untuk development dan demo tanpa kuota."""

from __future__ import annotations

import hashlib

from app.nlp.preprocess import tokenize

from .base import BaseAnalyzer, SentimentResult

TOPICS = (
    "harga", "rasa", "kemasan", "pengiriman", "pelayanan", "kualitas",
    "ukuran", "jahitan", "warna", "bahan", "promo",
)


class MockAnalyzer(BaseAnalyzer):
    name = "mock"

    async def analyze(
        self, items: list[tuple[str, str]]
    ) -> list[SentimentResult]:
        results: list[SentimentResult] = []
        for comment_id, text in items:
            value = int.from_bytes(
                hashlib.sha256(text.encode("utf-8")).digest()[:8], "big"
            )
            bucket = value % 100
            if bucket < 45:
                sentiment, score = "positif", 0.35 + (value % 61) / 100
            elif bucket < 80:
                sentiment, score = "negatif", -0.35 - (value % 61) / 100
            else:
                sentiment, score = "netral", ((value % 31) - 15) / 100
            tokens = set(tokenize(text))
            topics = [topic for topic in TOPICS if topic in tokens][:3]
            results.append(SentimentResult(
                id=comment_id,
                sentiment=sentiment,
                score=max(-1.0, min(1.0, score)),
                topics=topics,
            ))
        return results
