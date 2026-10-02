"""Collector replay untuk demo yang sepenuhnya offline."""

import csv
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

from app.models import CommentIn, Product

from .base import BaseCollector

logger = logging.getLogger(__name__)


class ReplayCollector(BaseCollector):
    name = "replay"

    def __init__(
        self,
        csv_path: str | Path = "tests/fixtures/replay_comments.csv",
        interval_seconds: float = 3.0,
        *,
        random_seed: int | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.csv_path = Path(csv_path)
        self._random = random.Random(random_seed)
        self._rows = self._load_rows()
        self._index = 0
        self._counter = 0

    def _load_rows(self) -> list[tuple[str, str]]:
        try:
            with self.csv_path.open(encoding="utf-8", newline="") as handle:
                rows = [
                    (row["product_id"].strip(), row["text"].strip())
                    for row in csv.DictReader(handle)
                    if row.get("product_id") and row.get("text")
                ]
        except (OSError, csv.Error, KeyError) as exc:
            logger.warning("Dataset replay tidak dapat dibaca: %s", exc)
            return []
        self._random.shuffle(rows)
        return rows

    async def collect(self, products: list[Product]) -> list[CommentIn]:
        if not self._rows:
            return []
        product_ids = {product.id for product in products}
        for _ in range(len(self._rows)):
            product_id, comment_text = self._rows[self._index]
            self._index = (self._index + 1) % len(self._rows)
            if product_id not in product_ids:
                continue
            now = datetime.now(timezone.utc)
            self._counter += 1
            unique_time = int(now.timestamp() * 1_000_000)
            return [
                CommentIn(
                    id=f"rp_{self._counter}_{unique_time}",
                    source=self.name,
                    product_id=product_id,
                    text=comment_text,
                    created_at=now,
                )
            ]
        return []
