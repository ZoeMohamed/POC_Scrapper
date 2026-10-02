"""Authenticated, source-specific refreshes for operational verification."""

from __future__ import annotations

import secrets
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.db import Database
from app.marketplace.collector import MarketplaceCollector
from app.social.collector import SocialCollector


RefreshSource = Literal["facebook", "shopee", "sentiment"]


class RefreshRequest(BaseModel):
    topic_id: str = Field(min_length=1, max_length=100)
    sources: list[RefreshSource] = Field(min_length=1, max_length=3)


def create_internal_refresh_router(
    database: Database,
    social: SocialCollector | None,
    marketplace: MarketplaceCollector | None,
    token: str,
) -> APIRouter:
    router = APIRouter(prefix="/api/internal", tags=["internal"])

    @router.post("/refresh")
    async def refresh(
        payload: RefreshRequest,
        supplied_token: str = Header(default="", alias="X-Refresh-Token"),
    ) -> dict[str, object]:
        if not token:
            raise HTTPException(status_code=404, detail="Endpoint tidak aktif")
        if not supplied_token or not secrets.compare_digest(supplied_token, token):
            raise HTTPException(status_code=401, detail="Token refresh tidak valid")
        topic = await database.get_topic(payload.topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail="Topik tidak ditemukan")

        results: dict[str, object] = {}
        for source in dict.fromkeys(payload.sources):
            try:
                if source == "facebook":
                    if social is None:
                        raise RuntimeError("Kolektor Facebook tidak dikonfigurasi")
                    counts = await social.refresh_platform(topic, "facebook")
                elif source == "shopee":
                    if marketplace is None:
                        raise RuntimeError("Kolektor Shopee tidak dikonfigurasi")
                    counts = await marketplace.refresh_topic(topic)
                else:
                    if social is None:
                        raise RuntimeError("Analisis sentimen sosial tidak dikonfigurasi")
                    counts = await social.analyze_pending(topic.id)
                results[source] = {"ok": True, "stored": counts}
            except Exception as exc:
                results[source] = {"ok": False, "error": str(exc)[:300]}

        if not any(
            isinstance(result, dict) and result.get("ok")
            for result in results.values()
        ):
            raise HTTPException(status_code=502, detail=results)
        return {"topic_id": topic.id, "results": results}

    return router
