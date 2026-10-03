"""Penghitung kata dan frasa yang deterministik."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .preprocess import tokenize

STOPWORDS_PATH = Path(__file__).with_name("stopwords_id.txt")


@lru_cache(maxsize=1)
def load_stopwords() -> frozenset[str]:
    """Muat stopword sekali; baris kosong dan komentar diabaikan."""

    with STOPWORDS_PATH.open(encoding="utf-8") as handle:
        return frozenset(
            line.strip().lower()
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        )


def _excluded_tokens(exclude: Iterable[str] | None) -> set[str]:
    phrases = [exclude] if isinstance(exclude, str) else (exclude or ())
    return {
        token
        for phrase in phrases
        for token in tokenize(str(phrase))
    }


def top_keywords(
    texts: Iterable[str],
    exclude: Iterable[str] | None,
    n: int = 10,
    ngram: int = 1,
) -> list[tuple[str, int]]:
    """Hitung unigram/bigram, diurutkan berdasarkan frekuensi lalu alfabet."""

    if ngram not in (1, 2):
        raise ValueError("ngram harus bernilai 1 atau 2")
    if n <= 0:
        return []
    blocked = set(load_stopwords()) | _excluded_tokens(exclude)
    counts: Counter[str] = Counter()
    for text in texts:
        tokens = [
            token for token in tokenize(text)
            if len(token) >= 3 and token not in blocked
        ]
        terms = tokens if ngram == 1 else [
            f"{left} {right}" for left, right in zip(tokens, tokens[1:])
        ]
        counts.update(terms)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:n]
