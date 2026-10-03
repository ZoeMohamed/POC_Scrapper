#!/usr/bin/env python3
"""Rebuild the v3 database and seed the configured watchlist topics."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402


def remove_database(path: Path) -> None:
    resolved = path.resolve()
    if resolved == PROJECT_ROOT or resolved.is_dir():
        raise ValueError(f"Target database tidak aman: {resolved}")
    for candidate in (resolved, Path(f"{resolved}-wal"), Path(f"{resolved}-shm")):
        if candidate.is_file():
            candidate.unlink()


async def reset() -> None:
    settings = Settings()
    remove_database(settings.database_path)
    database = Database(settings.database_path)
    await database.init()
    try:
        seeded = await database.seed_topics(settings.topics_path)
    finally:
        await database.close()
    print(f"Database {settings.database_path} dibuat ulang dengan {seeded} topik seed.")


if __name__ == "__main__":
    asyncio.run(reset())
