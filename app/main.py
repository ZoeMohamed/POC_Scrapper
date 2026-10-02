"""FastAPI entry point for the v3 trend and opinion dashboard."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analyzer.worker import AnalyzerWorker
from app.api.routes_feed import create_feed_router
from app.api.routes_health import create_health_router
from app.api.routes_ingest import create_ingest_router
from app.api.routes_products import create_products_router
from app.api.routes_stats import create_stats_router
from app.api.routes_stream import create_stream_router
from app.api.routes_summary import SummaryService, create_summary_router
from app.api.routes_topics import create_topics_router
from app.api.routes_maps import create_maps_router, create_places_compat_router
from app.api.routes_marketplace import create_marketplace_router
from app.api.routes_social import create_social_router
from app.api.routes_trend import create_trend_router
from app.api.routes_usage import create_usage_router
from app.collectors.runner import CollectorRunner, build_collectors
from app.config import Settings, get_settings
from app.db import Database
from app.db_postgres import PostgresDatabase
from app.events import EventBroker
from app.maps.usage import MapsUsageTracker
from app.maps.apify_client import ApifyMapsClient
from app.maps.collector import MapsCollector
from app.social.usage import SocialUsageTracker
from app.social.apify_client import SocialApifyClient
from app.social.collector import SocialCollector
from app.social.sentiment import SocialSentimentService
from app.marketplace.usage import MarketplaceUsageTracker
from app.marketplace.apify_client import ShopeeApifyClient
from app.marketplace.collector import MarketplaceCollector
from app.products import ProductCatalog
from app.topics.service import TopicService
from app.youtube.client import PublicYouTubeClient, YouTubeClient
from app.youtube.content_type import ContentTypeClassifier, GeminiTitleClassifier
from app.youtube.quota import QuotaTracker
from app.youtube.stats_snapshot import StatsSnapshotService
from app.youtube.trend_discovery import TrendDiscovery
from app.youtube.trend_scheduler import TrendScheduler

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
LEGACY_SOURCES = {"replay", "playstore", "inbox"}


def create_app(
    settings: Settings | None = None, *, start_background: bool = True
) -> FastAPI:
    runtime = settings or get_settings()
    use_postgres = runtime.database_backend == "postgres" or (
        runtime.database_backend == "auto" and bool(runtime.supabase_db_url)
    )
    if use_postgres:
        if not runtime.supabase_db_url:
            raise RuntimeError(
                "DATABASE_BACKEND=postgres membutuhkan SUPABASE_DB_URL"
            )
        database: Database = PostgresDatabase(
            runtime.supabase_db_url,
            comment_max_age_days=runtime.comment_max_age_days,
            auto_migrate=runtime.database_auto_migrate,
        )
    else:
        database = Database(
            runtime.database_path, comment_max_age_days=runtime.comment_max_age_days
        )
    catalog = ProductCatalog.from_path(runtime.products_path)
    broker = EventBroker()
    worker = AnalyzerWorker(runtime, database, broker)

    legacy = [source for source in runtime.active_sources if source in LEGACY_SOURCES]
    legacy_settings = runtime.model_copy(update={"sources": ",".join(legacy)})
    runner = CollectorRunner(
        legacy_settings, catalog, database, broker,
        collectors=build_collectors(legacy_settings, catalog.products),
    )
    youtube_quota = QuotaTracker(
        database, daily_quota=runtime.youtube_daily_quota,
        search_reserve=runtime.yt_search_reserve_units,
        demo_budget=runtime.demo_budget_units,
    )
    maps_usage = MapsUsageTracker(
        database, daily_cap=runtime.maps_daily_request_cap,
        monthly_cap=runtime.maps_monthly_request_cap,
    )
    social_usage = SocialUsageTracker(
        database,
        daily_cap=runtime.social_daily_run_cap,
        monthly_cap=runtime.social_monthly_run_cap,
    )
    marketplace_usage = MarketplaceUsageTracker(
        database,
        daily_cap=runtime.marketplace_daily_run_cap,
        monthly_cap=runtime.marketplace_monthly_run_cap,
    )
    maps_client: ApifyMapsClient | None = None
    maps_collector: MapsCollector | None = None
    if (
        "maps" in runtime.active_sources
        and runtime.maps_provider == "apify"
        and runtime.apify_maps_token_value
    ):
        maps_client = ApifyMapsClient(runtime, maps_usage)
        maps_collector = MapsCollector(database, maps_client, runtime, broker)
    social_client: SocialApifyClient | None = None
    social_collector: SocialCollector | None = None
    social_sentiment = SocialSentimentService(
        database, worker, broker,
        enabled=runtime.social_sentiment_enabled,
        batch_size=runtime.batch_size,
    )
    if (
        runtime.apify_social_token_value
        and {"tiktok", "instagram", "facebook"}.intersection(runtime.active_sources)
    ):
        social_client = SocialApifyClient(runtime, social_usage)
        social_collector = SocialCollector(
            database, social_client, runtime, broker, social_sentiment
        )
    marketplace_client: ShopeeApifyClient | None = None
    marketplace_collector: MarketplaceCollector | None = None
    if runtime.apify_marketplace_token_value and "shopee" in runtime.active_sources:
        marketplace_client = ShopeeApifyClient(runtime, marketplace_usage)
        marketplace_collector = MarketplaceCollector(database, marketplace_client, runtime, broker)
    youtube_client: YouTubeClient | PublicYouTubeClient | None = None
    if "youtube_trend" in runtime.active_sources:
        youtube_client = (
            YouTubeClient(
                runtime.youtube_api_key, youtube_quota,
                timeout=runtime.youtube_http_timeout_seconds,
            )
            if runtime.youtube_api_key
            else PublicYouTubeClient(timeout=runtime.youtube_http_timeout_seconds)
        )
    gemini_title_classifier = None
    if runtime.video_classifier == "auto" and runtime.gemini_api_key:
        try:
            gemini_title_classifier = GeminiTitleClassifier(runtime, worker.limiter)
        except (ImportError, RuntimeError, ValueError):
            logging.getLogger(__name__).warning(
                "Klasifikasi judul Gemini tidak tersedia; memakai aturan"
            )
    classifier = ContentTypeClassifier(
        runtime.video_classifier, gemini=gemini_title_classifier
    )
    discovery = (
        TrendDiscovery(database, youtube_client, runtime, classifier)
        if youtube_client else None
    )
    snapshot = (
        StatsSnapshotService(
            database, youtube_client, broker,
            usage_bucket="yt_demo" if runtime.demo_mode else "yt_read",
        )
        if youtube_client else None
    )
    trend_scheduler = TrendScheduler(
        runtime, database, broker, discovery, snapshot, maps_collector, social_collector,
        marketplace_collector
    )
    topic_service = TopicService(database, runtime)
    summary_service = SummaryService(database, runtime, worker=worker, limiter=worker.limiter)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=getattr(logging, runtime.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        )
        await database.init()
        await topic_service.seed()
        analyzer_task: asyncio.Task[None] | None = None
        if start_background:
            runner.start()
            trend_scheduler.start()
            analyzer_task = asyncio.create_task(worker.run(), name="analyzer-worker")
        application.state.settings = runtime
        application.state.database = database
        application.state.broker = broker
        application.state.trend_scheduler = trend_scheduler
        application.state.youtube_client = youtube_client
        application.state.youtube_quota = youtube_quota
        application.state.maps_usage = maps_usage
        application.state.social_usage = social_usage
        application.state.marketplace_usage = marketplace_usage
        application.state.maps_client = maps_client
        application.state.maps_collector = maps_collector
        application.state.social_client = social_client
        application.state.social_collector = social_collector
        application.state.marketplace_client = marketplace_client
        application.state.marketplace_collector = marketplace_collector
        application.state.social_sentiment = social_sentiment
        application.state.analyzer_worker = worker
        try:
            yield
        finally:
            await trend_scheduler.stop()
            await runner.stop()
            worker.stop()
            if analyzer_task is not None:
                try:
                    await asyncio.wait_for(analyzer_task, timeout=3)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    analyzer_task.cancel()
                    await asyncio.gather(analyzer_task, return_exceptions=True)
            if youtube_client:
                await youtube_client.close()
            if maps_client:
                await maps_client.close()
            if social_client:
                await social_client.close()
            if marketplace_client:
                await marketplace_client.close()
            await database.close()

    application = FastAPI(
        title="Pemantau Tren & Opini UMKM",
        description="Sinyal tren YouTube dan fondasi opini Google Maps untuk produk lokal.",
        version="3.0.0-p3",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(chrome-extension://[a-p]{32}|https?://(localhost|127\.0\.0\.1)(:\d+)?)$",
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-Ingest-Token"],
    )

    @application.middleware("http")
    async def no_stale_dashboard(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response
    application.include_router(
        create_health_router(runtime, worker, lambda: runtime.active_sources)
    )
    application.include_router(
        create_usage_router(
            youtube_quota,
            maps_usage,
            social_usage if {"tiktok", "instagram", "facebook"}.intersection(runtime.active_sources) else None,
            marketplace_usage if "shopee" in runtime.active_sources else None,
        )
    )
    application.include_router(
        create_topics_router(database, topic_service, trend_scheduler, runtime)
    )
    application.include_router(create_trend_router(database))
    application.include_router(create_maps_router(database))
    application.include_router(create_places_compat_router(database))
    application.include_router(create_social_router(database))
    application.include_router(create_marketplace_router(database))
    application.include_router(create_stream_router(broker))

    # Transitional v2 endpoints remain available while Maps opinion work starts at M4.
    application.include_router(create_products_router(catalog))
    application.include_router(create_feed_router(database, "30d"))
    application.include_router(create_stats_router(database, catalog, "30d"))
    application.include_router(create_summary_router(summary_service))
    application.include_router(create_ingest_router(database, catalog, broker, runtime))
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()
