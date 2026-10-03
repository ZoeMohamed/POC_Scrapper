"""Deterministic YouTube trend metrics from videos and immutable snapshots."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Iterable

from app.db import from_iso
from app.models import ContentMixItem, TopVideo, TrendMetrics, Video, WeeklyVideoCount

CONTENT_TYPES = ("review", "resep", "ide_usaha", "lainnya")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _change(current: float, previous: float) -> float | None:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 2)


def _trend(value: float | None) -> str:
    if value is None:
        return "butuh_data"
    if value >= 20:
        return "naik"
    if value <= -20:
        return "turun"
    return "stabil"


def _snapshot_map(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        captured = row.get("captured_at")
        if isinstance(captured, str):
            row["captured_at"] = from_iso(captured)
        result[str(row["video_id"])].append(row)
    for entries in result.values():
        entries.sort(key=lambda item: item["captured_at"])
    return result


def _at_or_before(rows: list[dict[str, Any]], target: datetime) -> dict[str, Any] | None:
    matches = [row for row in rows if row["captured_at"] <= target]
    return matches[-1] if matches else None


def _gain(rows: list[dict[str, Any]], hours: int) -> tuple[int, float] | None:
    if len(rows) < 2:
        return None
    latest = rows[-1]
    previous = _at_or_before(rows[:-1], latest["captured_at"] - timedelta(hours=hours))
    if previous is None:
        return None
    elapsed = max(1 / 60, (latest["captured_at"] - previous["captured_at"]).total_seconds() / 3600)
    return max(0, int(latest["views"]) - int(previous["views"])), elapsed


def _gain_between(
    rows: list[dict[str, Any]], start: datetime, end: datetime
) -> int | None:
    end_row = _at_or_before(rows, end)
    start_row = _at_or_before(rows, start)
    if not end_row or not start_row or end_row["captured_at"] <= start_row["captured_at"]:
        return None
    return max(0, int(end_row["views"]) - int(start_row["views"]))


def _weekly(videos: list[Video], now: datetime) -> list[WeeklyVideoCount]:
    current_monday = (now - timedelta(days=now.weekday())).date()
    starts = [current_monday - timedelta(weeks=index) for index in range(11, -1, -1)]
    counts = {start: 0 for start in starts}
    for video in videos:
        monday = (_utc(video.published_at) - timedelta(days=_utc(video.published_at).weekday())).date()
        if monday in counts:
            counts[monday] += 1
    return [WeeklyVideoCount(week_start=start.isoformat(), count=counts[start]) for start in starts]


def calculate_trend_metrics(
    topic_id: str, videos: list[Video], stat_rows: list[dict[str, Any]],
    *, now: datetime | None = None,
) -> TrendMetrics:
    current = _utc(now or datetime.now(timezone.utc))
    active = [video for video in videos if video.is_active]
    stats = _snapshot_map(stat_rows)
    last_times = [rows[-1]["captured_at"] for rows in stats.values() if rows]
    last_snapshot = max(last_times) if last_times else None
    latest_by_id = {video_id: rows[-1] for video_id, rows in stats.items() if rows}

    recent_30 = [video for video in active if current - timedelta(days=30) <= _utc(video.published_at) <= current]
    previous_30 = [video for video in active if current - timedelta(days=60) <= _utc(video.published_at) < current - timedelta(days=30)]
    supply_change = _change(len(recent_30), len(previous_30))

    view_rates: list[float] = []
    for video in recent_30:
        latest = latest_by_id.get(video.video_id)
        if latest:
            age_days = max(1, (current - _utc(video.published_at)).total_seconds() / 86400)
            view_rates.append(int(latest["views"]) / age_days)

    gain_1h_total = 0.0
    gain_24_total = 0
    current_pairs = 0
    gain_since_last = 0
    for video in active:
        rows = stats.get(video.video_id, [])
        one_hour = _gain(rows, 1)
        if one_hour:
            gain_1h_total += one_hour[0] / one_hour[1]
        day_gain = _gain(rows, 24)
        if day_gain:
            gain_24_total += day_gain[0]
            current_pairs += 1
        if len(rows) >= 2:
            gain_since_last += max(0, int(rows[-1]["views"]) - int(rows[-2]["views"]))

    enough_48h = bool(last_snapshot) and any(
        rows and rows[0]["captured_at"] <= last_snapshot - timedelta(hours=48)
        for rows in stats.values()
    )
    previous_gain = 0
    previous_pairs = 0
    if enough_48h and last_snapshot:
        for video in active:
            value = _gain_between(
                stats.get(video.video_id, []),
                last_snapshot - timedelta(hours=48), last_snapshot - timedelta(hours=24),
            )
            if value is not None:
                previous_gain += value
                previous_pairs += 1

    total_views = total_engagement = 0
    content_counts = {kind: 0 for kind in CONTENT_TYPES}
    content_views = {kind: 0 for kind in CONTENT_TYPES}
    for video in active:
        if current - _utc(video.published_at) > timedelta(days=90):
            continue
        latest = latest_by_id.get(video.video_id)
        views = int(latest["views"]) if latest else 0
        kind = video.content_type
        content_counts[kind] += 1
        content_views[kind] += views
        if latest:
            total_views += views
            total_engagement += int(latest.get("likes") or 0) + int(latest.get("comments") or 0)
    count_total = max(1, sum(content_counts.values()))
    views_total = max(1, sum(content_views.values()))
    content_mix = {
        kind: ContentMixItem(
            count=content_counts[kind], share=content_counts[kind] / count_total,
            views_share=content_views[kind] / views_total,
        ) for kind in CONTENT_TYPES
    }

    recent_idea = sum(video.content_type == "ide_usaha" for video in recent_30)
    previous_idea = sum(video.content_type == "ide_usaha" for video in previous_30)
    recent_share = recent_idea / max(1, len(recent_30))
    previous_share = previous_idea / max(1, len(previous_30))
    competition = "meningkat" if recent_idea >= 3 and recent_share > previous_share else "stabil"

    top: list[TopVideo] = []
    for video in active:
        latest = latest_by_id.get(video.video_id)
        if not latest:
            continue
        age_days = max(1, (current - _utc(video.published_at)).total_seconds() / 86400)
        day_gain = _gain(stats.get(video.video_id, []), 24)
        top.append(TopVideo(
            video_id=video.video_id, title=video.title,
            channel_title=video.channel_title, content_type=video.content_type,
            published_at=video.published_at, views=int(latest["views"]),
            views_per_day=round(int(latest["views"]) / age_days, 2),
            gain_24h=day_gain[0] if day_gain else None,
            url=f"https://www.youtube.com/watch?v={video.video_id}",
        ))
    top.sort(key=lambda item: (item.gain_24h or -1, item.views_per_day), reverse=True)

    hourly: dict[str, int] = defaultdict(int)
    if last_snapshot:
        cutoff = last_snapshot - timedelta(hours=48)
        for rows in stats.values():
            for before, after in zip(rows, rows[1:]):
                if after["captured_at"] >= cutoff:
                    key = after["captured_at"].replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
                    hourly[key] += max(0, int(after["views"]) - int(before["views"]))

    attention_change = _change(gain_24_total, previous_gain) if enough_48h and previous_pairs else None
    return TrendMetrics(
        topic_id=topic_id, videos_tracked=len(active),
        new_videos_30d=len(recent_30), new_videos_prev_30d=len(previous_30),
        supply_change_pct=supply_change, weekly_new_videos=_weekly(active, current),
        attention_index=round(median(view_rates), 2) if view_rates else None,
        views_gain_1h=round(gain_1h_total, 2) if gain_1h_total else None,
        views_gain_since_last=gain_since_last if gain_since_last or last_snapshot else None,
        views_gain_24h=gain_24_total if current_pairs else None,
        views_gain_prev_24h=previous_gain if enough_48h and previous_pairs else None,
        attention_change_pct=attention_change,
        coverage=current_pairs / len(active) if active else 0,
        engagement_rate=(total_engagement / total_views) if total_views else None,
        content_mix=content_mix,
        hourly_gain_series=[{"captured_at": key, "gain": hourly[key]} for key in sorted(hourly)],
        top_videos=top[:20], supply_trend=_trend(supply_change),
        attention_trend=_trend(attention_change), competition_signal=competition,
        last_snapshot_at=last_snapshot,
    )
