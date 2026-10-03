"""Product configuration loader."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from app.models import Product


def load_products(path: str | Path) -> list[Product]:
    """Load and validate products from JSON, rejecting duplicate identifiers."""
    product_path = Path(path)
    try:
        payload = json.loads(product_path.read_text(encoding="utf-8"))
        products = TypeAdapter(list[Product]).validate_python(payload)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Konfigurasi produk tidak ditemukan: {product_path}") from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"Konfigurasi produk tidak valid: {product_path}") from exc

    ids = [product.id for product in products]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Konfigurasi produk memiliki id duplikat")
    return products


class ProductCatalog:
    """Small immutable view over configured products."""

    def __init__(self, products: list[Product]) -> None:
        self.products = products
        self._by_id = {product.id: product for product in products}

    @classmethod
    def from_path(cls, path: str | Path) -> "ProductCatalog":
        return cls(load_products(path))

    def get(self, product_id: str) -> Product | None:
        return self._by_id.get(product_id)

    def keyword_exclusions(self, product_id: str | None = None) -> set[str]:
        selected = [self._by_id[product_id]] if product_id in self._by_id else self.products
        return {keyword.lower() for product in selected for keyword in product.keywords}
