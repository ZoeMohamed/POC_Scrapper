"""Collector file JSONL untuk integrasi script eksternal."""

import json
import logging
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.models import CommentIn, Product

from .base import BaseCollector

logger = logging.getLogger(__name__)


class InboxCollector(BaseCollector):
    name = "inbox"

    def __init__(
        self,
        inbox_path: str | Path = "data/inbox",
        interval_seconds: float = 90.0,
    ) -> None:
        self.inbox_path = Path(inbox_path)
        self.processed_path = self.inbox_path / "processed"
        self.interval_seconds = interval_seconds

    async def collect(self, products: list[Product]) -> list[CommentIn]:
        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.processed_path.mkdir(parents=True, exist_ok=True)
        allowed_products = {product.id for product in products}
        comments: list[CommentIn] = []
        for source_path in sorted(self.inbox_path.glob("*.jsonl")):
            comments.extend(self._read_file(source_path, allowed_products))
            self._move_processed(source_path)
        return comments

    def _read_file(self, path: Path, allowed_products: set[str]) -> list[CommentIn]:
        comments: list[CommentIn] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("File inbox %s gagal dibaca: %s", path, exc)
            return comments
        for line_number, line in enumerate(lines, start=1):
            try:
                payload: dict[str, Any] = json.loads(line)
                payload.setdefault("source", "inbox")
                if not payload.get("id"):
                    fingerprint = f"{payload.get('text', '')}{payload.get('created_at', '')}"
                    payload["id"] = "ib_" + sha256(
                        fingerprint.encode("utf-8")
                    ).hexdigest()[:16]
                comment = CommentIn.model_validate(payload)
                if comment.product_id not in allowed_products:
                    raise ValueError(f"product_id tidak dikenal: {comment.product_id}")
                comments.append(comment)
            except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
                logger.warning("%s:%d dilewati: %s", path, line_number, exc)
        return comments

    def _move_processed(self, source_path: Path) -> None:
        target = self.processed_path / source_path.name
        if target.exists():
            target = self.processed_path / (
                f"{source_path.stem}_{source_path.stat().st_mtime_ns}{source_path.suffix}"
            )
        try:
            shutil.move(str(source_path), target)
        except OSError as exc:
            logger.warning("File inbox %s gagal dipindahkan: %s", source_path, exc)
