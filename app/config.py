"""Application configuration loaded exclusively from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the v3 trend and opinion architecture."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    sources: str = "youtube_trend,maps"
    replay_interval_seconds: float = 4.0

    youtube_api_key: str = ""
    youtube_daily_quota: int = 10_000
    yt_search_reserve_units: int = 6_000
    yt_trend_lookback_days: int = 90
    yt_search_date_pages: int = 2
    yt_search_refresh_hours: float = 6.0
    yt_max_videos_per_topic: int = 150
    yt_stats_interval_minutes: float = 60.0
    yt_comments_enabled: bool = False
    # Negative search terms keep entertainment/noise out of the UMKM feed.
    # The same list is applied again after YouTube returns item details.
    yt_exclude_terms: str = (
        "upin ipin,kartun,animasi,animation,episode,full episode,serial,"
        "sinetron,dongeng,cerita anak,nursery,kids,kidz,balita,lagu,lagu anak,music video,"
        "official trailer,trailer,gaming,gameplay,meme,hiburan,komedi,parodi,"
        "sketsa,film anak,tayangan anak"
    )
    youtube_http_timeout_seconds: float = 10.0

    google_maps_api_key: str = ""
    # Apify is the POC provider for Google Maps reviews. The token is only
    # read by the server and is never sent to the browser.
    maps_provider: Literal["apify", "places"] = "apify"
    apify_token: str = ""
    # Optional per-service credentials isolate provider budgets. Each source
    # falls back to APIFY_TOKEN so existing deployments remain compatible.
    apify_maps_token: str = ""
    apify_social_token: str = ""
    apify_marketplace_token: str = ""
    apify_actor_id: str = "compass~crawler-google-places"
    apify_poll_interval_seconds: float = 5.0
    apify_poll_timeout_seconds: float = 600.0
    maps_language: str = "id"
    maps_max_places_per_search: int = 3
    maps_max_reviews_per_place: int = 10
    maps_refresh_hours: float = 8.0
    maps_daily_request_cap: int = 30
    maps_monthly_request_cap: int = 800
    maps_content_ttl_days: int = 7
    default_city: str = "Bandung"

    # Social trend discovery uses the same server-side Apify token. Defaults
    # favor broad post coverage without paid media downloads or comments.
    tiktok_actor_id: str = "clockworks~tiktok-scraper"
    instagram_actor_id: str = "apify~instagram-scraper"
    facebook_actor_id: str = "apify~facebook-search-scraper"
    social_results_per_query: int = 50
    # Facebook post search is cheaper than a media scraper; keep its payload
    # smaller than TikTok/Instagram while retaining enough trend evidence.
    facebook_results_per_query: int = 25
    social_max_queries_per_topic: int = 3
    social_lookback_days: int = 30
    social_refresh_hours: float = 12.0
    # Three social platforms share this budget. Eighteen runs cover one daily
    # refresh for six active topics without silently starving Facebook.
    social_daily_run_cap: int = 18
    social_monthly_run_cap: int = 450
    social_sentiment_enabled: bool = True

    # Marketplace discovery is intentionally one keyword run per topic. This
    # keeps Shopee useful for trend signals while preserving the Apify budget.
    shopee_actor_id: str = "xtracto~shopee-scraper"
    marketplace_results_per_query: int = 30
    marketplace_refresh_hours: float = 12.0
    marketplace_daily_run_cap: int = 8
    marketplace_monthly_run_cap: int = 200

    demo_mode: bool = False
    demo_stats_interval_seconds: float = 120.0
    demo_budget_units: int = 1_500
    max_active_topics: int = 20

    ai_mode: Literal["mock", "lexicon", "gemini"] = "mock"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_rpm: int = 8
    batch_size: int = 25
    batch_max_wait_seconds: float = 10.0
    max_gemini_failures: int = 3
    video_classifier: Literal["auto", "rules"] = "auto"

    database_path: Path = Path("data/app.db")
    # ``auto`` keeps local development on SQLite and selects Supabase Postgres
    # when SUPABASE_DB_URL is present. The URL is server-only and must never be
    # exposed to the browser.
    database_backend: Literal["auto", "sqlite", "postgres"] = "auto"
    supabase_db_url: str = ""
    # Schema changes are deployed through Supabase migrations. Keep runtime DDL
    # disabled on serverless to avoid concurrent catalog updates on cold starts.
    database_auto_migrate: bool = False
    topics_path: Path = Path("config/topics.json")
    max_comment_chars: int = 800
    log_level: str = "INFO"

    # Compatibility-only settings retained while the v2 modules remain importable.
    products_path: Path = Path("config/products.json")
    inbox_path: Path = Path("data/inbox")
    seed_comments_path: Path = Path("data/seed_comments.csv")
    collect_interval_seconds: float = 90.0
    youtube_videos_per_product: int = 5
    youtube_search_refresh_minutes: int = 60
    comment_max_age_days: int = 180
    marketplace_ingest_token: str = ""

    @field_validator(
        "youtube_daily_quota", "yt_search_reserve_units", "yt_trend_lookback_days",
        "yt_search_date_pages", "yt_max_videos_per_topic",
        "maps_max_places_per_search", "maps_max_reviews_per_place",
        "maps_daily_request_cap", "maps_monthly_request_cap", "maps_content_ttl_days",
        "social_results_per_query", "social_max_queries_per_topic",
        "social_lookback_days", "social_daily_run_cap", "social_monthly_run_cap",
        "marketplace_results_per_query", "marketplace_daily_run_cap", "marketplace_monthly_run_cap",
        "demo_budget_units", "max_active_topics", "gemini_rpm", "batch_size",
        "max_gemini_failures", "max_comment_chars",
        "comment_max_age_days",
    )
    @classmethod
    def positive_integer(cls, value: int) -> int:
        if value < 1:
            raise ValueError("nilai harus lebih besar dari nol")
        return value

    @field_validator(
        "replay_interval_seconds", "yt_search_refresh_hours", "yt_stats_interval_minutes",
        "youtube_http_timeout_seconds", "maps_refresh_hours",
        "apify_poll_interval_seconds", "apify_poll_timeout_seconds",
        "social_refresh_hours", "marketplace_refresh_hours",
        "demo_stats_interval_seconds", "batch_max_wait_seconds",
        "collect_interval_seconds",
    )
    @classmethod
    def positive_interval(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("interval harus lebih besar dari nol")
        return value

    @field_validator("sources", mode="before")
    @classmethod
    def normalize_sources(cls, value: object) -> str:
        if isinstance(value, (list, tuple, set)):
            return ",".join(str(item) for item in value)
        return str(value)

    @property
    def active_sources(self) -> list[str]:
        aliases = {
            "youtube": "youtube_trend", "gmaps": "maps",
            "ig": "instagram", "tiktok_trend": "tiktok", "fb": "facebook",
        }
        values = (
            aliases.get(part.strip().lower(), part.strip().lower())
            for part in self.sources.split(",")
            if part.strip()
        )
        return list(dict.fromkeys(values))

    @property
    def youtube_exclude_terms(self) -> list[str]:
        """Return normalized, de-duplicated YouTube noise terms."""

        return list(dict.fromkeys(
            term.strip() for term in self.yt_exclude_terms.split(",") if term.strip()
        ))

    @property
    def apify_maps_token_value(self) -> str:
        return self.apify_maps_token or self.apify_token

    @property
    def apify_social_token_value(self) -> str:
        return self.apify_social_token or self.apify_token

    @property
    def apify_marketplace_token_value(self) -> str:
        return self.apify_marketplace_token or self.apify_token


@lru_cache
def get_settings() -> Settings:
    return Settings()
