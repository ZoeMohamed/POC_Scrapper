from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Video
from app.youtube.trend_metrics import calculate_trend_metrics


def make_video(video_id: str, kind: str, published_at: datetime) -> Video:
    return Video(video_id=video_id, topic_id="kopi", title=f"Video {video_id}", channel_id="c", channel_title="Kreator", published_at=published_at, discovered_at=published_at, discovery_source="search_date", content_type=kind)


def test_metrics_use_immutable_snapshots_for_velocity() -> None:
    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    videos = [make_video("one", "review", now - timedelta(days=5)), make_video("two", "ide_usaha", now - timedelta(days=10))]
    rows = []
    for video_id, base in (("one", 1000), ("two", 2000)):
        rows.extend([
            {"video_id": video_id, "captured_at": (now - timedelta(hours=48)).isoformat(), "views": base, "likes": 10, "comments": 2},
            {"video_id": video_id, "captured_at": (now - timedelta(hours=24)).isoformat(), "views": base + 100, "likes": 12, "comments": 3},
            {"video_id": video_id, "captured_at": now.isoformat(), "views": base + 350, "likes": 14, "comments": 4},
        ])

    metrics = calculate_trend_metrics("kopi", videos, rows, now=now)

    assert metrics.videos_tracked == 2
    assert metrics.views_gain_24h == 500
    assert metrics.views_gain_prev_24h == 200
    assert metrics.attention_change_pct == 150.0
    assert metrics.coverage == 1.0
    assert metrics.content_mix["review"].count == 1
    assert len(metrics.top_videos) == 2
