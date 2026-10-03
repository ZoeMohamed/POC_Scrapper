from datetime import datetime, timedelta, timezone

from app.youtube.parsing import relative_datetime


def test_public_youtube_indonesian_abbreviated_age() -> None:
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    assert relative_datetime({"simpleText": "2 mgg lalu"}, now=now) == now - timedelta(weeks=2)
    assert relative_datetime({"simpleText": "3 bln lalu"}, now=now) == now - timedelta(days=90)
    assert relative_datetime({"simpleText": "2 thn lalu"}, now=now) == now - timedelta(days=730)
