"""Kontrak bersama untuk seluruh analyzer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

try:  # Pakai model aplikasi jika lapisan model menyediakannya.
    from app.models import SentimentResult as SentimentResult  # type: ignore
except (ImportError, AttributeError):
    class SentimentResult(BaseModel):
        id: str
        sentiment: Literal["positif", "negatif", "netral"]
        score: float = Field(ge=-1.0, le=1.0)
        topics: list[str] = Field(default_factory=list, max_items=3)


class AnalyzerError(RuntimeError):
    """Kegagalan analyzer yang boleh dicoba ulang oleh worker."""


class RateLimitedError(AnalyzerError):
    """Kuota analyzer eksternal sedang dibatasi."""


class BaseAnalyzer(ABC):
    name: str

    @abstractmethod
    async def analyze(
        self, items: list[tuple[str, str]]
    ) -> list[SentimentResult]:
        """Analisis pasangan ``(id komentar, teks)``."""
