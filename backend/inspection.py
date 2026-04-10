import asyncio
import logging
import time
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

# Global progress tracking: check_id -> {completed, total, status, elapsed_seconds}
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


async def _create_service_pool(loop, count: int, credentials_path: str = None, token_path: str = None) -> asyncio.Queue:
    """Create a pool of GSC service instances for thread-safe concurrent use."""
    pool: asyncio.Queue = asyncio.Queue()
    for _ in range(count):
        svc = await loop.run_in_executor(None, get_searchconsole_service, credentials_path, token_path)
        pool.put_nowait(svc)
    return pool


async def _batch_preprocess_urls(db, urls: list[str]) -> dict:
    """Batch upsert URLs and fetch their IDs and previous verdicts.

    Returns {url: {"url_id": int, "prev_verdict": str|None}} for each URL.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Batch insert all URLs at once
    await db.executemany(
        "INSERT OR IGNORE INTO urls (url, first_seen) VALUES (?, ?)",
        [(url, now) for url in urls],
    )

    # Batch fetch all URL IDs
    placeholders = ",".join("?" for _ in urls)
    cursor = await db.execute(
        f"SELECT id, url, deindex_count FROM urls WHERE url IN ({placeholders})",
        urls,
    )
    rows = await cursor.fetchall()
    url_info = {row[1]: {"url_id": row[0], "deindex_count": row[2]} for row in rows}

    # Batch fetch previous verdicts for all url_ids
    url_ids = [info["url_id"] for info in url_info.values()]
    if url_ids:
        id_placeholders = ",".join("?" for _ in url_ids)
        cursor = await db.execute(
            f"""SELECT url_id, verdict FROM results
                WHERE id IN (
                    SELECT MAX(id) FROM results
                    WHERE url_id IN ({id_placeholders}) AND error IS NULL
                    GROUP BY url_id
                )""",
            url_ids,
        )
        verdict_rows = await cursor.fetchall()
        verdict_map = {row[0]: row[1] for row in verdict_rows}
    else:
        verdict_map = {}

    # Merge prev_verdict into url_info
    for url, info in url_info.items():
        info["prev_verdict"] = verdict_map.get(info["url_id"])

    await db.commit()
    return url_info


async def _process_single_url(
    loop,
    db,
    service_pool: asyncio.Queue,
    rate_limiter: RateLimiter,
    check_id: int,
    url: str,
    url_id: int,
    prev_verdict: Optional[str],
    progress: dict,
    quota_exhausted: asyncio.Event,
    profile_id: int = None,
):
    """Process a single URL: inspect via API and store result."""
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

    try:
        # Rate limit, then acquire service only for the API call
        await rate_limiter.acquire()

        service = await service_pool.get()
        try:
            response = await loop.run_in_executor(None, inspect_url, service, url, GSC_PROPERTY_URL)
        finally:
            await service_pool.put(service)

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


async def run_inspection(check_id: int, urls: list[str]):
    """Run inspection for all URLs concurrently with per-profile service pools."""
    loop = asyncio.get_event_loop()
    start_time = time.monotonic()
    progress = {"completed": 0, "total": len(urls), "status": "running", "elapsed_seconds": 0.0, "started_at": start_time}
    progress_store[check_id] = progress

    db = await get_db()
    try:
        # Batch pre-process: upsert all URLs, fetch IDs and previous verdicts
        url_info = await _batch_preprocess_urls(db, urls)

        # Load profiles and group URLs
        profiles = await get_all_profiles(db)

        if profiles:
            # Multi-profile mode: group URLs by profile
            grouped, unmatched = group_urls_by_profile(urls, profiles)
            profiles_by_id = {p["id"]: p for p in profiles}

            # Reserve quota per profile upfront
            for pid, profile_urls in grouped.items():
                count = len(profile_urls)
                current_used = await increment_profile_quota_usage(db, pid, count)
                if current_used > DAILY_QUOTA_LIMIT:
                    logger.warning(f"Profile {pid} quota would be exhausted: {current_used}/{DAILY_QUOTA_LIMIT}")

            # Create per-profile service pools and rate limiters
            service_pools: dict[int, asyncio.Queue] = {}
            rate_limiters: dict[int, RateLimiter] = {}
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
                    rate_limiters[pid] = RateLimiter(MAX_REQUESTS_PER_MINUTE / 60.0)
                    quota_events[pid] = asyncio.Event()
                except Exception as e:
                    logger.error(f"Failed to init service pool for profile '{profile['name']}': {e}")
                    for url in profile_urls:
                        info = url_info.get(url)
                        if info:
                            await db.execute(
                                """INSERT INTO results
                                   (check_id, url_id, coverage_state, verdict, last_crawl_time,
                                    crawled_as, google_canonical, user_canonical, referring_sitemaps,
                                    status_changed, error, profile_id)
                                   VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, ?)""",
                                (check_id, info["url_id"], f"Profile '{profile['name']}' auth failed: {e}", pid),
                            )
                        progress["completed"] += 1
                    await db.commit()

            # Build tasks for all profiled URLs
            tasks = []
            for pid, profile_urls in grouped.items():
                if pid not in service_pools:
                    continue
                for url in profile_urls:
                    info = url_info.get(url, {})
                    tasks.append(
                        _process_single_url(
                            loop, db, service_pools[pid], rate_limiters[pid],
                            check_id, url, info.get("url_id"), info.get("prev_verdict"),
                            progress, quota_events[pid],
                            profile_id=pid,
                        )
                    )

            # Handle unmatched URLs — insert error results
            for url in unmatched:
                info = url_info.get(url)
                if info:
                    await db.execute(
                        """INSERT INTO results
                           (check_id, url_id, coverage_state, verdict, last_crawl_time,
                            crawled_as, google_canonical, user_canonical, referring_sitemaps,
                            status_changed, error, profile_id)
                           VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, NULL)""",
                        (check_id, info["url_id"], "No matching profile for URL path"),
                    )
                progress["completed"] += 1
            await db.commit()

            # Run all profiled URL tasks concurrently
            await asyncio.gather(*tasks, return_exceptions=True)

        else:
            # Legacy single-credential mode (no profiles configured)
            # Reserve quota upfront for entire batch
            current_used = await increment_quota_usage(db, count=len(urls))
            if current_used > DAILY_QUOTA_LIMIT:
                logger.warning(f"Quota would be exhausted: {current_used}/{DAILY_QUOTA_LIMIT}")

            try:
                service_pool = await _create_service_pool(loop, CONCURRENCY_LIMIT)
            except Exception as e:
                logger.error(f"Failed to initialize GSC service pool: {e}")
                elapsed = time.monotonic() - start_time
                progress_store[check_id]["status"] = "error"
                progress_store[check_id]["elapsed_seconds"] = elapsed
                await db.execute(
                    "UPDATE checks SET status = 'error', elapsed_seconds = ? WHERE id = ?",
                    (elapsed, check_id),
                )
                await db.commit()
                await db.close()
                return

            rate_limiter = RateLimiter(MAX_REQUESTS_PER_MINUTE / 60.0)
            quota_exhausted = asyncio.Event()
            tasks = [
                _process_single_url(
                    loop, db, service_pool, rate_limiter,
                    check_id, url,
                    url_info.get(url, {}).get("url_id"),
                    url_info.get(url, {}).get("prev_verdict"),
                    progress, quota_exhausted,
                )
                for url in urls
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Final commit for all pending writes
        await db.commit()

        # Record elapsed time and mark check as completed
        elapsed = time.monotonic() - start_time
        await db.execute(
            "UPDATE checks SET status = 'completed', elapsed_seconds = ? WHERE id = ?",
            (elapsed, check_id),
        )
        await db.commit()
        progress_store[check_id]["status"] = "completed"
        progress_store[check_id]["elapsed_seconds"] = elapsed

    except Exception as e:
        logger.error(f"Check {check_id} failed: {e}")
        elapsed = time.monotonic() - start_time
        await db.execute(
            "UPDATE checks SET status = 'error', elapsed_seconds = ? WHERE id = ?",
            (elapsed, check_id),
        )
        await db.commit()
        progress_store[check_id]["status"] = "error"
        progress_store[check_id]["elapsed_seconds"] = elapsed
    finally:
        await db.close()
