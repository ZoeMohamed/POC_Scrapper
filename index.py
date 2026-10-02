"""Vercel entrypoint for the FastAPI dashboard.

Vercel's Python runtime discovers an ASGI app exposed as ``app`` from a root
``index.py``.  The local deployment keeps its SQLite file under ``data/``;
Vercel's function filesystem is read-only, so the serverless fallback uses
``/tmp``. For durable production data, set the server-only ``SUPABASE_DB_URL``
environment variable; the app then selects Supabase Postgres automatically.
"""

from __future__ import annotations

import os

# Keep the hosted POC on the same live sources as the local dashboard. Vercel
# project environment variables override these defaults without changing code.
os.environ.setdefault("SOURCES", "youtube_trend,maps,tiktok,instagram,facebook,shopee")
os.environ.setdefault("AI_MODE", "lexicon")
os.environ.setdefault("DATABASE_PATH", "/tmp/umkm-poc.db")

from app.main import create_app  # noqa: E402  (runtime defaults must be set first)

# A serverless request must not spawn an endless scheduler. Multiple Vercel
# instances previously ran the same refresh concurrently, causing Supabase
# row locks and duplicate Apify spend. Topic creation and the authenticated
# bounded refresh endpoint still perform explicit collection work.
app = create_app(start_background=False)

__all__ = ["app"]
