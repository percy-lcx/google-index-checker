import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from gsc_auth import get_searchconsole_service
from database import get_db
from config import GSC_PROPERTY_URL, API_DELAY_MS

logger = logging.getLogger(__name__)

# Global progress tracking: check_id -> {completed, total, status}
progress_store: dict[int, dict] = {}


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


async def run_inspection(check_id: int, urls: list[str]):
    """Run inspection for all URLs in background."""
    loop = asyncio.get_event_loop()
    progress_store[check_id] = {"completed": 0, "total": len(urls), "status": "running"}

    try:
        service = await loop.run_in_executor(None, get_searchconsole_service)
    except Exception as e:
        logger.error(f"Failed to initialize GSC service: {e}")
        progress_store[check_id]["status"] = "error"
        db = await get_db()
        try:
            await db.execute("UPDATE checks SET status = 'error' WHERE id = ?", (check_id,))
            await db.commit()
        finally:
            await db.close()
        return

    db = await get_db()
    try:
        for url in urls:
            now = datetime.now(timezone.utc).isoformat()

            # Upsert URL record
            await db.execute(
                "INSERT OR IGNORE INTO urls (url, first_seen) VALUES (?, ?)",
                (url, now),
            )
            cursor = await db.execute("SELECT id, deindex_count FROM urls WHERE url = ?", (url,))
            url_row = await cursor.fetchone()
            url_id = url_row[0]
            deindex_count = url_row[1]

            # Get previous verdict for transition detection
            prev_verdict = await get_previous_verdict(db, url_id)

            try:
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
                        status_changed, error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
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
                    ),
                )

            except Exception as e:
                logger.error(f"Inspection failed for {url}: {e}")
                await db.execute(
                    """INSERT INTO results
                       (check_id, url_id, coverage_state, verdict, last_crawl_time,
                        crawled_as, google_canonical, user_canonical, referring_sitemaps,
                        status_changed, error)
                       VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?)""",
                    (check_id, url_id, str(e)),
                )

            await db.commit()
            progress_store[check_id]["completed"] += 1

            # Rate limiting delay
            await asyncio.sleep(API_DELAY_MS / 1000.0)

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
