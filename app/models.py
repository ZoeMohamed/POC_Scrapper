"""Pydantic contracts shared by collectors, storage, API, and UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TopicCategory = Literal["makanan_minuman", "kecantikan", "fashion", "umum"]
TopicStatus = Literal["discovering", "active", "limited", "inactive"]
ContentType = Literal["review", "resep", "ide_usaha", "lainnya"]
Sentiment = Literal["positif", "negatif", "netral"]
Status = Literal["pending", "analyzed", "failed"]
AnalyzerName = Literal["gemini", "lexicon", "mock"]
ReviewCategory = Literal["opini_produk", "opini_tempat", "lainnya"]
SourceName = Literal[
    "gmaps", "replay", "youtube", "playstore", "inbox",
    "tokopedia", "shopee", "tiktokshop",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Topic(ApiModel):
    id: str
    name: str
    category: TopicCategory = "umum"
    keywords: list[str]
    product_terms: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)
    cities: list[str]
    own_place_id: str | None = None
    status: TopicStatus = "discovering"
    is_seed: bool = False
    is_active: bool = True
    created_at: datetime
    yt_last_discovery_at: datetime | None = None
    maps_last_refresh_at: datetime | None = None


class TopicCreate(ApiModel):
    name: str = Field(min_length=2, max_length=60)
    keywords: list[str] = Field(min_length=1, max_length=5)
    product_terms: list[str] = Field(min_length=1, max_length=8)
    exclude_terms: list[str] = Field(default_factory=list, max_length=8)
    category: TopicCategory = "umum"
    cities: list[str] = Field(min_length=1, max_length=3)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("keywords", "product_terms", "exclude_terms", "cities")
    @classmethod
    def clean_items(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.split()) for value in values if value.strip()]
        if len(cleaned) != len(set(item.casefold() for item in cleaned)):
            raise ValueError("nilai tidak boleh duplikat")
        return cleaned


class Video(ApiModel):
    video_id: str
    topic_id: str
    title: str
    channel_id: str
    channel_title: str
    description: str = ""
    published_at: datetime
    discovered_at: datetime
    discovery_source: Literal["search_date", "search_viewcount", "public_search"]
    content_type: ContentType = "lainnya"
    is_active: bool = True


class VideoStat(ApiModel):
    video_id: str
    captured_at: datetime
    views: int = Field(ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)


class WeeklyVideoCount(ApiModel):
    week_start: str
    count: int


class ContentMixItem(ApiModel):
    count: int
    share: float
    views_share: float


class TopVideo(ApiModel):
    video_id: str
    title: str
    channel_title: str
    content_type: ContentType
    published_at: datetime
    views: int
    views_per_day: float
    gain_24h: int | None
    url: str


class TrendMetrics(ApiModel):
    topic_id: str
    videos_tracked: int = 0
    new_videos_30d: int = 0
    new_videos_prev_30d: int = 0
    supply_change_pct: float | None = None
    weekly_new_videos: list[WeeklyVideoCount] = Field(default_factory=list)
    attention_index: float | None = None
    views_gain_1h: float | None = None
    views_gain_since_last: int | None = None
    views_gain_24h: int | None = None
    views_gain_prev_24h: int | None = None
    attention_change_pct: float | None = None
    coverage: float = 0.0
    engagement_rate: float | None = None
    content_mix: dict[str, ContentMixItem] = Field(default_factory=dict)
    hourly_gain_series: list[dict[str, int | str]] = Field(default_factory=list)
    top_videos: list[TopVideo] = Field(default_factory=list)
    supply_trend: Literal["naik", "turun", "stabil"] = "stabil"
    attention_trend: Literal["naik", "turun", "stabil", "butuh_data"] = "butuh_data"
    competition_signal: Literal["meningkat", "stabil"] = "stabil"
    last_snapshot_at: datetime | None = None


# Legacy contracts retained so v2 analyzer modules can coexist during migration.
class CommentIn(ApiModel):
    id: str = Field(min_length=1)
    source: SourceName
    product_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    url: str | None = None
    author_hash: str | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Comment(CommentIn):
    collected_at: datetime
    topic_id: str | None = None
    place_id: str | None = None
    text_is_translated: bool = False
    stars: int | None = Field(default=None, ge=1, le=5)
    author_name: str | None = None
    author_uri: str | None = None
    mentions_product: bool = False
    category: ReviewCategory | None = None
    expires_at: datetime | None = None
    status: Status = "pending"
    sentiment: Sentiment | None = None
    score: Annotated[float, Field(ge=-1.0, le=1.0)] | None = None
    topics: list[str] = Field(default_factory=list, max_length=3)
    analyzer: AnalyzerName | None = None
    attempts: int = Field(default=0, ge=0)


class SentimentResult(ApiModel):
    id: str
    sentiment: Sentiment
    score: float
    topics: list[str] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def clamp_score(cls, value: float) -> float:
        return max(-1.0, min(1.0, value))

    @field_validator("topics")
    @classmethod
    def clean_topics(cls, values: list[str]) -> list[str]:
        return [value.strip().lower() for value in values if value.strip()][:3]


class Product(ApiModel):
    id: str
    name: str
    keywords: list[str] = Field(default_factory=list)
    playstore_app_ids: list[str] = Field(default_factory=list)


class CountItem(ApiModel):
    word: str
    count: int = Field(ge=0)


class TopicCount(ApiModel):
    topic: str
    count: int = Field(ge=0)


class Stats(ApiModel):
    product_id: str | None
    window: Literal["1h", "24h", "7d", "30d", "90d", "all"]
    total: int
    sentiment: dict[str, int]
    top_keywords: list[CountItem]
    top_topics: list[TopicCount]
    by_source: dict[str, int]


class Summary(ApiModel):
    summary: str
    praises: list[str] = Field(default_factory=list, max_length=3)
    complaints: list[str] = Field(default_factory=list, max_length=3)
    innovation_ideas: list[str] = Field(default_factory=list, max_length=3)
    generated_at: datetime
    analyzer: Literal["gemini", "template"]
