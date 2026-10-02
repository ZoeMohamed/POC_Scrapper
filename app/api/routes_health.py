"""Application health API."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from app.config import Settings


def _state_from(worker: Any | None) -> dict[str, Any]:
    if worker is None:
        return {}
    state = getattr(worker, "state", worker)
    if callable(state):
        state = state()
    if hasattr(state, "model_dump"):
        state = state.model_dump(mode="json")
    return dict(state) if isinstance(state, dict) else {}


def create_health_router(
    settings: Settings,
    worker: Any | None = None,
    sources_provider: Callable[[], list[str]] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["system"])

    @router.get("/health")
    async def health() -> dict[str, object]:
        sources = sources_provider() if sources_provider else settings.active_sources
        maps_apify_token = settings.apify_maps_token_value
        social_apify_token = settings.apify_social_token_value
        marketplace_apify_token = settings.apify_marketplace_token_value
        analyzer = _state_from(worker) or {
            "ai_mode": settings.ai_mode,
            "active_analyzer": settings.ai_mode,
            "gemini_healthy": settings.ai_mode != "gemini" or bool(settings.gemini_api_key),
            "cooldown_until": None,
            "last_error": None,
            "pending_count": 0,
        }
        return {
            "status": "ok",
            "database_backend": (
                "postgres"
                if settings.database_backend == "postgres"
                or (settings.database_backend == "auto" and bool(settings.supabase_db_url))
                else "sqlite"
            ),
            "sources_active": sources,
            "youtube_configured": bool(settings.youtube_api_key),
            "youtube_mode": "api" if settings.youtube_api_key else "public",
            "maps_provider": settings.maps_provider,
            "maps_configured": bool(
                (maps_apify_token and "maps" in sources) if settings.maps_provider == "apify"
                else (settings.google_maps_api_key and "maps" in sources)
            ),
            "apify_configured": bool(
                maps_apify_token or social_apify_token or marketplace_apify_token
            ),
            "tiktok_configured": bool(
                social_apify_token and "tiktok" in sources
            ),
            "instagram_configured": bool(
                social_apify_token and "instagram" in sources
            ),
            "facebook_configured": bool(
                social_apify_token and "facebook" in sources
            ),
            "shopee_configured": bool(
                marketplace_apify_token and "shopee" in sources
            ),
            "max_active_topics": settings.max_active_topics,
            "social_daily_run_cap": settings.social_daily_run_cap,
            "social_monthly_run_cap": settings.social_monthly_run_cap,
            "marketplace_results_per_query": settings.marketplace_results_per_query,
            "marketplace_daily_run_cap": settings.marketplace_daily_run_cap,
            "marketplace_monthly_run_cap": settings.marketplace_monthly_run_cap,
            "social_sentiment_enabled": settings.social_sentiment_enabled,
            "social_sentiment_analyzer": analyzer.get("active_analyzer", settings.ai_mode),
            "yt_comments_enabled": settings.yt_comments_enabled,
            "demo_mode": settings.demo_mode,
            "analyzer": analyzer,
            "source_messages": {
                "youtube": (
                    "YouTube Data API aktif"
                    if settings.youtube_api_key
                    else "Mode publik YouTube aktif; tambahkan API key untuk kuota resmi"
                ),
                "maps": (
                    "Google Maps tidak diaktifkan pada SOURCES"
                    if "maps" not in sources
                    else f"Apify Google Maps aktif ({settings.apify_actor_id})"
                    if settings.maps_provider == "apify" and maps_apify_token
                    else "Google Maps Places aktif"
                    if settings.maps_provider == "places" and settings.google_maps_api_key
                    else "Google Maps belum dikonfigurasi"
                ),
                "tiktok": (
                    f"TikTok Apify aktif ({settings.tiktok_actor_id})"
                    if social_apify_token and "tiktok" in sources
                    else "TikTok Apify belum dikonfigurasi"
                ),
                "instagram": (
                    f"Instagram Apify aktif ({settings.instagram_actor_id})"
                    if social_apify_token and "instagram" in sources
                    else "Instagram Apify belum dikonfigurasi"
                ),
                "facebook": (
                    f"Facebook Apify aktif ({settings.facebook_actor_id})"
                    if social_apify_token and "facebook" in sources
                    else "Facebook Apify belum dikonfigurasi"
                ),
                "shopee": (
                    f"Shopee Apify aktif ({settings.shopee_actor_id})"
                    if marketplace_apify_token and "shopee" in sources
                    else "Shopee Apify belum dikonfigurasi"
                ),
            },
        }

    return router
