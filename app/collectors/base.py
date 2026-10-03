"""Kontrak bersama untuk semua collector."""

from abc import ABC, abstractmethod
from hashlib import sha256

from app.models import CommentIn, Product


def hash_author(value: str | None) -> str | None:
    """Hash identitas penulis agar nama/ID asli tidak pernah disimpan."""
    if not value:
        return None
    return sha256(value.encode("utf-8")).hexdigest()


class BaseCollector(ABC):
    """Interface collector asinkron yang dapat dijalankan oleh runner."""

    name: str
    interval_seconds: float

    @abstractmethod
    async def collect(self, products: list[Product]) -> list[CommentIn]:
        """Ambil komentar baru; kegagalan sumber dikembalikan sebagai list kosong."""

    async def close(self) -> None:
        """Lepaskan resource milik collector, jika ada."""
