import aiosqlite
from datetime import datetime, timedelta, timezone

from config import DATABASE_PATH, RETENTION_DAYS

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
        """)
        await db.commit()
    finally:
        await db.close()


async def run_retention_cleanup():
    """Purge results older than RETENTION_DAYS. Remove orphan checks."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    db = await get_db()
    try:
        await db.execute("DELETE FROM results WHERE check_id IN (SELECT id FROM checks WHERE created_at < ?)", (cutoff,))
        await db.execute("DELETE FROM checks WHERE id NOT IN (SELECT DISTINCT check_id FROM results)")
        await db.commit()
    finally:
        await db.close()


async def get_daily_quota_used() -> int:
    """Count inspections performed today."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT COUNT(*) as cnt FROM results r
               JOIN checks c ON r.check_id = c.id
               WHERE c.created_at >= ? AND r.error IS NULL""",
            (today_start,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
    finally:
        await db.close()
