"""Configured product API."""

from fastapi import APIRouter

from app.models import Product
from app.products import ProductCatalog


def create_products_router(products: ProductCatalog | list[Product]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["products"])
    items = products.products if isinstance(products, ProductCatalog) else products

    @router.get("/products", response_model=list[Product])
    async def get_products() -> list[Product]:
        return items

    return router
