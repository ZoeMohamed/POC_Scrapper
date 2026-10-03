"""Copy the local scraper database into the private Supabase schema.

This command is intentionally additive: existing remote rows are preserved and
duplicate primary/unique keys are skipped. The whole copy runs in one Postgres
transaction so a failed backup does not leave a partially imported database.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db_postgres import POSTGRES_SCHEMA


TABLES = (
    "topics",
    "videos",
    "video_stats",
    "places",
    "place_snapshots",
    "comments",
    "summaries",
    "social_posts",
    "social_post_stats",
    "social_refreshes",
    "marketplace_products",
    "marketplace_refreshes",
    "api_usage",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backup SQLite scraper data to Supabase Postgres"
    )
    parser.add_argument("--source", default="data/app.db", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect source row counts without connecting to Supabase",
    )
    return parser.parse_args()


def read_source(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        raise SystemExit(f"Database sumber tidak ditemukan: {path}")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        return {
            table: [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
            for table in TABLES
            if table in existing
        }
    finally:
        connection.close()


async def copy_to_supabase(
    dsn: str, source: dict[str, list[dict[str, Any]]]
) -> dict[str, dict[str, int]]:
    connection = await asyncpg.connect(
        dsn=dsn,
        command_timeout=60,
        statement_cache_size=0,
        server_settings={
            "search_path": "scraper,public",
            "application_name": "umkm-poc-backup",
        },
    )
    summary: dict[str, dict[str, int]] = {}
    try:
        await connection.execute(POSTGRES_SCHEMA)
        async with connection.transaction():
            for table in TABLES:
                rows = source.get(table, [])
                before = int(
                    await connection.fetchval(f'SELECT count(*) FROM scraper."{table}"')
                )
                if rows:
                    columns = list(rows[0])
                    names = ", ".join(f'"{column}"' for column in columns)
                    params = ", ".join(
                        f"${number}" for number in range(1, len(columns) + 1)
                    )
                    query = (
                        f'INSERT INTO scraper."{table}" ({names}) '
                        f"VALUES ({params}) ON CONFLICT DO NOTHING"
                    )
                    await connection.executemany(
                        query,
                        [tuple(row[column] for column in columns) for row in rows],
                    )
                after = int(
                    await connection.fetchval(f'SELECT count(*) FROM scraper."{table}"')
                )
                summary[table] = {
                    "source": len(rows),
                    "inserted": max(0, after - before),
                    "remote_total": after,
                }
    finally:
        await connection.close()
    return summary


async def main() -> None:
    args = parse_args()
    source = read_source(args.source)
    if args.dry_run:
        for table in TABLES:
            print(f"{table}: {len(source.get(table, []))} rows")
        return

    dsn = os.getenv("SUPABASE_DB_URL", "").strip()
    if not dsn:
        raise SystemExit(
            "SUPABASE_DB_URL belum diisi. Gunakan connection string pooler server-side."
        )
    result = await copy_to_supabase(dsn, source)
    for table, counts in result.items():
        print(
            f"{table}: source={counts['source']} inserted={counts['inserted']} "
            f"remote_total={counts['remote_total']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
