"""Combined YouTube and Maps usage endpoint."""

from fastapi import APIRouter

from app.maps.usage import MapsUsageTracker
from app.youtube.quota import QuotaTracker
from app.social.usage import SocialUsageTracker
from app.marketplace.usage import MarketplaceUsageTracker


def create_usage_router(
    youtube: QuotaTracker, maps: MapsUsageTracker,
    social: SocialUsageTracker | None = None,
    marketplace: MarketplaceUsageTracker | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["usage"])

    @router.get("/usage")
    async def usage() -> dict[str, object]:
        payload: dict[str, object] = {
            "youtube": await youtube.status(), "maps": await maps.status()
        }
        if social:
            payload["social"] = await social.status()
        if marketplace:
            payload["marketplace"] = await marketplace.status()
        return payload

    return router
