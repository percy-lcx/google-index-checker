import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from googleapiclient.errors import HttpError

from gsc_auth import get_searchconsole_service
from database import (
    get_db, increment_quota_usage, force_quota_exhausted,
    increment_profile_quota_usage, force_profile_quota_exhausted,
)
from profiles import get_all_profiles, group_urls_by_profile
from config import GSC_PROPERTY_URL, CONCURRENCY_LIMIT, MAX_REQUESTS_PER_MINUTE, DAILY_QUOTA_LIMIT

logger = logging.getLogger(__name__)

# Global progress tracking: check_id -> {completed, total, status}
progress_store: dict[int, dict] = {}


class RateLimiter:
    """Async rate limiter that enforces a maximum requests-per-second rate."""

    def __init__(self, max_per_second: float):
        self._interval = 1.0 / max_per_second
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._last + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = asyncio.get_event_loop().time()


def inspect_url(service, url: str, property_url: str) -> dict:
    """Call the URL Inspection API synchronously (run in executor)."""
    body = {
        "inspectionUrl": url,
        "siteUrl": property_url,
    }
    response = service.urlInspection().index().inspect(body=body).execute()
    return response


def parse_inspection_result(response: dict) -> dict:
    """Extract relevant fields from the API response."""
    result = response.get("inspectionResult", {})
    index_status = result.get("indexStatusResult", {})

    return {
        "coverage_state": index_status.get("coverageState"),
        "verdict": index_status.get("verdict"),
        "last_crawl_time": index_status.get("lastCrawlTime"),
        "crawled_as": index_status.get("crawlingUserAgent"),
        "google_canonical": index_status.get("googleCanonical"),
        "user_canonical": index_status.get("userCanonical"),
        "referring_sitemaps": ",".join(index_status.get("sitemap", [])) if index_status.get("sitemap") else None,
    }


async def get_previous_verdict(db, url_id: int) -> Optional[str]:
    """Get the most recent verdict for a URL."""
    cursor = await db.execute(
        """SELECT verdict FROM results
           WHERE url_id = ? AND error IS NULL
           ORDER BY id DESC LIMIT 1""",
        (url_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def _create_service_pool(loop, count: int, credentials_path: str = None, token_path: str = None) -> asyncio.Queue:
    """Create a pool of GSC service instances for thread-safe concurrent use."""
    pool: asyncio.Queue = asyncio.Queue()
    for _ in range(count):
        svc = await loop.run_in_executor(None, get_searchconsole_service, credentials_path, token_path)
        pool.put_nowait(svc)
    return pool


async def _process_single_url(
    loop,
    db,
    service_pool: asyncio.Queue,
    rate_limiter: RateLimiter,
    check_id: int,
    url: str,
    progress: dict,
    quota_exhausted: asyncio.Event,
    profile_id: int = None,
):
    """Process a single URL: inspect via API and store result."""
    service = await service_pool.get()
    try:
        now = datetime.now(timezone.utc).isoformat()

        # Upsert URL record
        await db.execute(
            "INSERT OR IGNORE INTO urls (url, first_seen) VALUES (?, ?)",
            (url, now),
        )
        cursor = await db.execute("SELECT id, deindex_count FROM urls WHERE url = ?", (url,))
        url_row = await cursor.fetchone()
        url_id = url_row[0]

        # Check if quota was exhausted by another worker
        if quota_exhausted.is_set():
            await db.execute(
                """INSERT INTO results
                   (check_id, url_id, coverage_state, verdict, last_crawl_time,
                    crawled_as, google_canonical, user_canonical, referring_sitemaps,
                    status_changed, error, profile_id)
                   VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, ?)""",
                (check_id, url_id, "Quota exhausted", profile_id),
            )
            progress["completed"] += 1
            return

        # Reserve quota BEFORE the API call
        if profile_id:
            current_used = await increment_profile_quota_usage(db, profile_id)
        else:
            current_used = await increment_quota_usage(db)
        if current_used > DAILY_QUOTA_LIMIT:
            logger.warning(f"Quota exhausted mid-batch at {current_used}/{DAILY_QUOTA_LIMIT}")
            quota_exhausted.set()
            await db.execute(
                """INSERT INTO results
                   (check_id, url_id, coverage_state, verdict, last_crawl_time,
                    crawled_as, google_canonical, user_canonical, referring_sitemaps,
                    status_changed, error, profile_id)
                   VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, ?)""",
                (check_id, url_id, "Quota exhausted", profile_id),
            )
            progress["completed"] += 1
            return

        # Get previous verdict for transition detection
        prev_verdict = await get_previous_verdict(db, url_id)

        try:
            # Rate limit before API call
            await rate_limiter.acquire()
            response = await loop.run_in_executor(None, inspect_url, service, url, GSC_PROPERTY_URL)
            parsed = parse_inspection_result(response)

            # Transition detection
            status_changed = False
            current_verdict = parsed["verdict"]
            if prev_verdict is not None and current_verdict is not None:
                was_indexed = prev_verdict == "PASS"
                is_indexed = current_verdict == "PASS"
                if was_indexed != is_indexed:
                    status_changed = True
                    # Indexed -> Deindexed transition
                    if was_indexed and not is_indexed:
                        await db.execute(
                            "UPDATE urls SET deindex_count = deindex_count + 1 WHERE id = ?",
                            (url_id,),
                        )

            await db.execute(
                """INSERT INTO results
                   (check_id, url_id, coverage_state, verdict, last_crawl_time,
                    crawled_as, google_canonical, user_canonical, referring_sitemaps,
                    status_changed, error, profile_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)""",
                (
                    check_id,
                    url_id,
                    parsed["coverage_state"],
                    parsed["verdict"],
                    parsed["last_crawl_time"],
                    parsed["crawled_as"],
                    parsed["google_canonical"],
                    parsed["user_canonical"],
                    parsed["referring_sitemaps"],
                    status_changed,
                    profile_id,
                ),
            )

        except HttpError as e:
            if e.resp.status == 429:
                logger.warning(f"Google API returned 429 for {url}. Quota exhausted on Google side.")
                if profile_id:
                    await force_profile_quota_exhausted(db, profile_id)
                else:
                    await force_quota_exhausted(db)
                quota_exhausted.set()
                await db.execute(
                    """INSERT INTO results
                       (check_id, url_id, coverage_state, verdict, last_crawl_time,
                        crawled_as, google_canonical, user_canonical, referring_sitemaps,
                        status_changed, error, profile_id)
                       VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, ?)""",
                    (check_id, url_id, "Google quota exhausted (HTTP 429)", profile_id),
                )
            else:
                logger.error(f"Inspection failed for {url}: {e}")
                await db.execute(
                    """INSERT INTO results
                       (check_id, url_id, coverage_state, verdict, last_crawl_time,
                        crawled_as, google_canonical, user_canonical, referring_sitemaps,
                        status_changed, error, profile_id)
                       VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, ?)""",
                    (check_id, url_id, str(e), profile_id),
                )

        except Exception as e:
            logger.error(f"Inspection failed for {url}: {e}")
            await db.execute(
                """INSERT INTO results
                   (check_id, url_id, coverage_state, verdict, last_crawl_time,
                    crawled_as, google_canonical, user_canonical, referring_sitemaps,
                    status_changed, error, profile_id)
                   VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, ?)""",
                (check_id, url_id, str(e), profile_id),
            )

        progress["completed"] += 1

    finally:
        await service_pool.put(service)


async def run_inspection(check_id: int, urls: list[str]):
    """Run inspection for all URLs concurrently with per-profile service pools."""
    loop = asyncio.get_event_loop()
    progress = {"completed": 0, "total": len(urls), "status": "running"}
    progress_store[check_id] = progress

    db = await get_db()
    try:
        # Load profiles and group URLs
        profiles = await get_all_profiles(db)

        if profiles:
            # Multi-profile mode: group URLs by profile
            grouped, unmatched = group_urls_by_profile(urls, profiles)
            profiles_by_id = {p["id"]: p for p in profiles}

            # Create per-profile service pools
            service_pools: dict[int, asyncio.Queue] = {}
            # Per-profile quota exhaustion events
            quota_events: dict[int, asyncio.Event] = {}

            for pid, profile_urls in grouped.items():
                profile = profiles_by_id[pid]
                try:
                    pool = await _create_service_pool(
                        loop, min(CONCURRENCY_LIMIT, len(profile_urls)),
                        credentials_path=profile["credentials_path"],
                        token_path=profile["token_path"],
                    )
                    service_pools[pid] = pool
                    quota_events[pid] = asyncio.Event()
                except Exception as e:
                    logger.error(f"Failed to init service pool for profile '{profile['name']}': {e}")
                    # Mark all URLs in this profile as errors
                    now = datetime.now(timezone.utc).isoformat()
                    for url in profile_urls:
                        await db.execute("INSERT OR IGNORE INTO urls (url, first_seen) VALUES (?, ?)", (url, now))
                        cursor = await db.execute("SELECT id FROM urls WHERE url = ?", (url,))
                        url_row = await cursor.fetchone()
                        await db.execute(
                            """INSERT INTO results
                               (check_id, url_id, coverage_state, verdict, last_crawl_time,
                                crawled_as, google_canonical, user_canonical, referring_sitemaps,
                                status_changed, error, profile_id)
                               VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, ?)""",
                            (check_id, url_row[0], f"Profile '{profile['name']}' auth failed: {e}", pid),
                        )
                        progress["completed"] += 1
                    await db.commit()

            rate_limiter = RateLimiter(MAX_REQUESTS_PER_MINUTE / 60.0)

            # Build tasks for all profiled URLs
            tasks = []
            for pid, profile_urls in grouped.items():
                if pid not in service_pools:
                    continue  # Already handled as errors above
                for url in profile_urls:
                    tasks.append(
                        _process_single_url(
                            loop, db, service_pools[pid], rate_limiter,
                            check_id, url, progress, quota_events[pid],
                            profile_id=pid,
                        )
                    )

            # Handle unmatched URLs — insert error results
            now = datetime.now(timezone.utc).isoformat()
            for url in unmatched:
                await db.execute("INSERT OR IGNORE INTO urls (url, first_seen) VALUES (?, ?)", (url, now))
                cursor = await db.execute("SELECT id FROM urls WHERE url = ?", (url,))
                url_row = await cursor.fetchone()
                await db.execute(
                    """INSERT INTO results
                       (check_id, url_id, coverage_state, verdict, last_crawl_time,
                        crawled_as, google_canonical, user_canonical, referring_sitemaps,
                        status_changed, error, profile_id)
                       VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, NULL)""",
                    (check_id, url_row[0], "No matching profile for URL path"),
                )
                progress["completed"] += 1
            await db.commit()

            # Run all profiled URL tasks concurrently
            await asyncio.gather(*tasks, return_exceptions=True)

        else:
            # Legacy single-credential mode (no profiles configured)
            try:
                service_pool = await _create_service_pool(loop, CONCURRENCY_LIMIT)
            except Exception as e:
                logger.error(f"Failed to initialize GSC service pool: {e}")
                progress_store[check_id]["status"] = "error"
                await db.execute("UPDATE checks SET status = 'error' WHERE id = ?", (check_id,))
                await db.commit()
                await db.close()
                return

            rate_limiter = RateLimiter(MAX_REQUESTS_PER_MINUTE / 60.0)
            quota_exhausted = asyncio.Event()
            tasks = [
                _process_single_url(loop, db, service_pool, rate_limiter, check_id, url, progress, quota_exhausted)
                for url in urls
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Final commit for all pending writes
        await db.commit()

        # Mark check as completed
        await db.execute("UPDATE checks SET status = 'completed' WHERE id = ?", (check_id,))
        await db.commit()
        progress_store[check_id]["status"] = "completed"

    except Exception as e:
        logger.error(f"Check {check_id} failed: {e}")
        await db.execute("UPDATE checks SET status = 'error' WHERE id = ?", (check_id,))
        await db.commit()
        progress_store[check_id]["status"] = "error"
    finally:
        await db.close()
