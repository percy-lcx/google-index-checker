import json

import aiosqlite
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config import DATABASE_PATH, DAILY_QUOTA_LIMIT, RETENTION_DAYS

# Google's daily API quotas reset at midnight Pacific Time
PACIFIC = ZoneInfo("America/Los_Angeles")


def today_pacific() -> str:
    """Return today's date in Pacific Time (matches Google's quota reset)."""
    return datetime.now(PACIFIC).strftime("%Y-%m-%d")

DB_PATH = DATABASE_PATH


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                first_seen DATETIME NOT NULL,
                deindex_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at DATETIME NOT NULL,
                url_count INTEGER NOT NULL,
                property_url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running'
            );

            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                check_id INTEGER NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
                url_id INTEGER NOT NULL REFERENCES urls(id),
                coverage_state TEXT,
                verdict TEXT,
                last_crawl_time DATETIME,
                crawled_as TEXT,
                google_canonical TEXT,
                user_canonical TEXT,
                referring_sitemaps TEXT,
                status_changed BOOLEAN DEFAULT 0,
                error TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_results_check_id ON results(check_id);
            CREATE INDEX IF NOT EXISTS idx_results_url_id ON results(url_id);

            CREATE TABLE IF NOT EXISTS quota_usage (
                date TEXT PRIMARY KEY,
                used INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                site_url TEXT NOT NULL,
                path_pattern TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS property_quota_usage (
                date TEXT NOT NULL,
                property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
                used INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (date, property_id)
            );

            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_watchlist_sort ON watchlist(sort_order);

            CREATE TABLE IF NOT EXISTS schedule_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                times TEXT NOT NULL,
                timezone TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
        """)

        # Seed the singleton schedule_settings row on first init
        cursor = await db.execute("SELECT 1 FROM schedule_settings WHERE id = 1")
        if not await cursor.fetchone():
            await db.execute(
                "INSERT INTO schedule_settings (id, times, timezone, enabled) VALUES (1, ?, ?, 1)",
                (json.dumps(["07:00", "17:00"]), "Asia/Hong_Kong"),
            )
            await db.commit()
        # Migration: drop any legacy credentials tables and rebuild results with property_id.
        # Handles both the original "profiles" schema and the interim "credentials" schema.
        cursor = await db.execute("PRAGMA table_info(results)")
        results_cols = [row[1] for row in await cursor.fetchall()]
        needs_rebuild = (
            "property_id" not in results_cols
            and any(col in results_cols for col in ("credential_id", "profile_id"))
        )
        if needs_rebuild:
            await db.executescript("""
                PRAGMA foreign_keys=OFF;

                CREATE TABLE results_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id INTEGER NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
                    url_id INTEGER NOT NULL REFERENCES urls(id),
                    coverage_state TEXT,
                    verdict TEXT,
                    last_crawl_time DATETIME,
                    crawled_as TEXT,
                    google_canonical TEXT,
                    user_canonical TEXT,
                    referring_sitemaps TEXT,
                    status_changed BOOLEAN DEFAULT 0,
                    error TEXT,
                    property_id INTEGER REFERENCES properties(id)
                );

                INSERT INTO results_new
                    (id, check_id, url_id, coverage_state, verdict, last_crawl_time,
                     crawled_as, google_canonical, user_canonical, referring_sitemaps,
                     status_changed, error, property_id)
                SELECT
                    id, check_id, url_id, coverage_state, verdict, last_crawl_time,
                    crawled_as, google_canonical, user_canonical, referring_sitemaps,
                    status_changed, error, NULL
                FROM results;

                DROP TABLE results;
                ALTER TABLE results_new RENAME TO results;

                CREATE INDEX IF NOT EXISTS idx_results_check_id ON results(check_id);
                CREATE INDEX IF NOT EXISTS idx_results_url_id ON results(url_id);

                DROP TABLE IF EXISTS credential_quota_usage;
                DROP TABLE IF EXISTS credentials;
                DROP TABLE IF EXISTS profile_quota_usage;
                DROP TABLE IF EXISTS profiles;

                PRAGMA foreign_keys=ON;
            """)
            await db.commit()

        # Migration: add property_id to results if missing (fresh-install path)
        cursor = await db.execute("PRAGMA table_info(results)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "property_id" not in columns:
            await db.execute("ALTER TABLE results ADD COLUMN property_id INTEGER REFERENCES properties(id)")
            await db.commit()

        # Migration: drop orphan credentials/profiles tables on fresh rebuilds too
        for legacy_table in ("credential_quota_usage", "credentials", "profile_quota_usage", "profiles"):
            await db.execute(f"DROP TABLE IF EXISTS {legacy_table}")
        await db.commit()

        # Migration: add elapsed_seconds to checks if missing
        cursor = await db.execute("PRAGMA table_info(checks)")
        check_columns = [row[1] for row in await cursor.fetchall()]
        if "elapsed_seconds" not in check_columns:
            await db.execute("ALTER TABLE checks ADD COLUMN elapsed_seconds REAL")
            await db.commit()

        # Migration: add source to checks if missing
        if "source" not in check_columns:
            await db.execute("ALTER TABLE checks ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
            await db.commit()

        await db.commit()
    finally:
        await db.close()


async def get_watchlist() -> list[str]:
    """Return the watchlist URLs in saved order."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT url FROM watchlist ORDER BY sort_order, id"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        await db.close()


async def replace_watchlist(urls: list[str]) -> int:
    """Atomically replace the entire watchlist. Returns the new count."""
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.execute("BEGIN")
        await db.execute("DELETE FROM watchlist")
        for i, url in enumerate(urls):
            await db.execute(
                "INSERT OR IGNORE INTO watchlist (url, sort_order, created_at) VALUES (?, ?, ?)",
                (url, i, now),
            )
        await db.commit()
        cursor = await db.execute("SELECT COUNT(*) FROM watchlist")
        row = await cursor.fetchone()
        return row[0]
    finally:
        await db.close()


async def has_running_scheduled_check() -> bool:
    """True if any scheduled check is still in the 'running' state."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT 1 FROM checks WHERE source = 'scheduled' AND status = 'running' LIMIT 1"
        )
        row = await cursor.fetchone()
        return row is not None
    finally:
        await db.close()


async def get_schedule_settings() -> dict:
    """Return the singleton schedule row as a dict."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT times, timezone, enabled FROM schedule_settings WHERE id = 1"
        )
        row = await cursor.fetchone()
        if not row:
            return {
                "times": ["07:00", "17:00"],
                "timezone": "Asia/Hong_Kong",
                "enabled": True,
            }
        return {
            "times": json.loads(row[0]),
            "timezone": row[1],
            "enabled": bool(row[2]),
        }
    finally:
        await db.close()


async def save_schedule_settings(times: list[str], timezone_name: str, enabled: bool) -> None:
    """Replace the singleton schedule row. Caller has already validated inputs."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO schedule_settings (id, times, timezone, enabled) VALUES (1, ?, ?, ?)",
            (json.dumps(times), timezone_name, 1 if enabled else 0),
        )
        await db.commit()
    finally:
        await db.close()


async def run_retention_cleanup():
    """Purge results older than RETENTION_DAYS. Remove orphan checks and old quota rows."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    db = await get_db()
    try:
        await db.execute("DELETE FROM results WHERE check_id IN (SELECT id FROM checks WHERE created_at < ?)", (cutoff,))
        await db.execute("DELETE FROM checks WHERE id NOT IN (SELECT DISTINCT check_id FROM results)")
        await db.execute("DELETE FROM quota_usage WHERE date < ?", (cutoff_date,))
        await db.commit()
    finally:
        await db.close()


async def get_daily_quota_used() -> int:
    """Read today's quota usage from the quota_usage table."""
    today = today_pacific()
    db = await get_db()
    try:
        cursor = await db.execute("SELECT used FROM quota_usage WHERE date = ?", (today,))
        row = await cursor.fetchone()
        return row[0] if row else 0
    finally:
        await db.close()


async def increment_quota_usage(db: aiosqlite.Connection, count: int = 1) -> int:
    """Atomically increment today's quota counter. Returns new total."""
    today = today_pacific()
    await db.execute(
        "INSERT INTO quota_usage (date, used) VALUES (?, ?) "
        "ON CONFLICT(date) DO UPDATE SET used = used + ?",
        (today, count, count),
    )
    await db.commit()
    cursor = await db.execute("SELECT used FROM quota_usage WHERE date = ?", (today,))
    row = await cursor.fetchone()
    return row[0]


async def force_quota_exhausted(db: aiosqlite.Connection):
    """Mark today's quota as fully exhausted (e.g. after a Google 429)."""
    today = today_pacific()
    await db.execute(
        "INSERT INTO quota_usage (date, used) VALUES (?, ?) "
        "ON CONFLICT(date) DO UPDATE SET used = ?",
        (today, DAILY_QUOTA_LIMIT, DAILY_QUOTA_LIMIT),
    )
    await db.commit()


async def get_property_quota_used(property_id: int) -> int:
    """Read today's quota usage for a specific property."""
    today = today_pacific()
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT used FROM property_quota_usage WHERE date = ? AND property_id = ?",
            (today, property_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
    finally:
        await db.close()


async def increment_property_quota_usage(db: aiosqlite.Connection, property_id: int, count: int = 1) -> int:
    """Atomically increment today's quota counter for a property. Returns new total."""
    today = today_pacific()
    await db.execute(
        "INSERT INTO property_quota_usage (date, property_id, used) VALUES (?, ?, ?) "
        "ON CONFLICT(date, property_id) DO UPDATE SET used = used + ?",
        (today, property_id, count, count),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT used FROM property_quota_usage WHERE date = ? AND property_id = ?",
        (today, property_id),
    )
    row = await cursor.fetchone()
    return row[0]


async def force_property_quota_exhausted(db: aiosqlite.Connection, property_id: int):
    """Mark today's quota as fully exhausted for a property."""
    today = today_pacific()
    await db.execute(
        "INSERT INTO property_quota_usage (date, property_id, used) VALUES (?, ?, ?) "
        "ON CONFLICT(date, property_id) DO UPDATE SET used = ?",
        (today, property_id, DAILY_QUOTA_LIMIT, DAILY_QUOTA_LIMIT),
    )
    await db.commit()


async def get_all_properties_quota() -> list[dict]:
    """Get today's quota usage for all properties, ordered by sort_order."""
    today = today_pacific()
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT p.id, p.name, p.site_url, COALESCE(pq.used, 0) as used
               FROM properties p
               LEFT JOIN property_quota_usage pq ON p.id = pq.property_id AND pq.date = ?
               ORDER BY p.sort_order, p.id""",
            (today,),
        )
        rows = await cursor.fetchall()
        return [
            {"property_id": row[0], "name": row[1], "site_url": row[2], "used": row[3]}
            for row in rows
        ]
    finally:
        await db.close()


async def seed_quota_from_results():
    """One-time migration: if quota_usage has no row for today, seed it from existing results."""
    today = today_pacific()
    # Midnight Pacific in UTC for querying checks.created_at (stored as UTC)
    pacific_midnight = datetime.now(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = pacific_midnight.astimezone(timezone.utc).isoformat()
    db = await get_db()
    try:
        cursor = await db.execute("SELECT used FROM quota_usage WHERE date = ?", (today,))
        row = await cursor.fetchone()
        if row is not None:
            return  # Already tracking today

        # Count today's results from the results table as a best-effort seed
        cursor = await db.execute(
            """SELECT COUNT(*) FROM results r
               JOIN checks c ON r.check_id = c.id
               WHERE c.created_at >= ?""",
            (today_start,),
        )
        count_row = await cursor.fetchone()
        count = count_row[0] if count_row else 0
        if count > 0:
            await db.execute(
                "INSERT OR IGNORE INTO quota_usage (date, used) VALUES (?, ?)",
                (today, count),
            )
            await db.commit()
    finally:
        await db.close()
