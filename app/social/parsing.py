"""Normalize TikTok and Instagram post rows into one small contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.models import Topic
from app.nlp.preprocess import normalize

from .apify_client import Platform


@dataclass(frozen=True)
class SocialPost:
    platform: Platform
    post_id: str
    text: str
    author_name: str | None
    author_url: str | None
    url: str | None
    published_at: datetime
    views: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    query: str | None
    mentions_product: bool


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def _date(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, timezone.utc)
    else:
        raw = _text(value)
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _contains_product(text: str, topic: Topic) -> bool:
    haystack = normalize(text)
    signals = [topic.name, *topic.keywords, *topic.product_terms]
    return any(normalize(signal) and normalize(signal) in haystack for signal in signals)


def parse_social_items(
    platform: Platform,
    items: list[dict[str, Any]],
    topic: Topic,
    *,
    now: datetime | None = None,
) -> list[SocialPost]:
    fallback = now or datetime.now(timezone.utc)
    if fallback.tzinfo is None:
        fallback = fallback.replace(tzinfo=timezone.utc)
    output: list[SocialPost] = []
    for item in items:
        if platform == "tiktok":
            author = item.get("authorMeta") or item.get("author") or {}
            author_name = (
                _text(author.get("name") or author.get("nickName") or author.get("uniqueId")) or None
                if isinstance(author, dict) else None
            )
            post_id = _text(item.get("id") or item.get("videoId"))
            text = _text(item.get("text") or item.get("desc") or item.get("description"))
            url = _text(item.get("webVideoUrl") or item.get("videoUrl")) or None
            author_url = (
                _text(author.get("profileUrl")) or None if isinstance(author, dict) else None
            )
            published = item.get("createTimeISO") or item.get("createTime")
            views = _int(item.get("playCount") or item.get("play_count") or item.get("views"))
            likes = _int(item.get("diggCount") or item.get("likes"))
            comments = _int(item.get("commentCount") or item.get("comments"))
            shares = _int(item.get("shareCount") or item.get("shares"))
            query = _text(item.get("searchQuery")) or None
        elif platform == "instagram":
            owner = item.get("owner") or item.get("ownerMeta") or {}
            author_name = (
                _text(item.get("ownerUsername") or owner.get("username") or owner.get("fullName")) or None
                if isinstance(owner, dict) else _text(item.get("ownerUsername")) or None
            )
            post_id = _text(item.get("id") or item.get("pk") or item.get("shortCode"))
            text = _text(item.get("caption") or item.get("captionText") or item.get("text"))
            shortcode = _text(item.get("shortCode") or item.get("shortcode"))
            url = _text(item.get("url")) or (
                f"https://www.instagram.com/p/{shortcode}/" if shortcode else ""
            ) or None
            author_url = (
                _text(owner.get("profileUrl")) or None if isinstance(owner, dict) else None
            )
            published = item.get("timestamp") or item.get("takenAt") or item.get("taken_at_timestamp")
            views = _int(item.get("videoViewCount") or item.get("videoPlayCount") or item.get("plays"))
            edge_likes = item.get("edge_liked_by")
            edge_comments = item.get("edge_media_to_comment")
            like_value = item.get("likesCount") or item.get("likes")
            if like_value is None and isinstance(edge_likes, dict):
                like_value = edge_likes.get("count")
            comment_value = item.get("commentsCount") or item.get("comments")
            if comment_value is None and isinstance(edge_comments, dict):
                comment_value = edge_comments.get("count")
            likes = _int(like_value)
            comments = _int(comment_value)
            shares = _int(item.get("sharesCount") or item.get("shares"))
            query = _text(item.get("sourceHashtag") or item.get("search")) or None
        else:
            author = item.get("author") or item.get("owner") or item.get("page") or {}
            author_name = (
                _text(item.get("authorName") or item.get("userName") or item.get("pageName") or author.get("name") or author.get("username")) or None
                if isinstance(author, dict) else _text(item.get("authorName") or item.get("userName")) or None
            )
            post_id = _text(item.get("postId") or item.get("post_id") or item.get("id") or item.get("legacyId"))
            text = _text(item.get("text") or item.get("postText") or item.get("message") or item.get("description"))
            url = _text(item.get("url") or item.get("postUrl") or item.get("post_url")) or None
            author_url = _text(item.get("authorUrl") or author.get("url") or author.get("profileUrl")) or None if isinstance(author, dict) else None
            published = item.get("publishedAt") or item.get("published_at") or item.get("timestamp") or item.get("time") or item.get("date")
            views = _int(item.get("views") or item.get("videoViews") or item.get("viewCount"))
            likes = _int(item.get("likes") or item.get("likesCount") or item.get("reactionCount"))
            comments = _int(item.get("comments") or item.get("commentsCount") or item.get("commentCount"))
            shares = _int(item.get("shares") or item.get("sharesCount") or item.get("shareCount"))
            query = _text(item.get("searchQuery") or item.get("query") or item.get("category")) or None
        if not post_id or not text:
            continue
        output.append(SocialPost(
            platform=platform, post_id=post_id, text=text, author_name=author_name,
            author_url=author_url, url=url, published_at=_date(published, fallback),
            views=views, likes=likes, comments=comments, shares=shares, query=query,
            mentions_product=_contains_product(text, topic),
        ))
    return output
