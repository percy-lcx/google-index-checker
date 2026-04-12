import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from config import GSC_PROPERTY_URL, DAILY_QUOTA_LIMIT
from database import get_db, get_daily_quota_used
from inspection import run_inspection


class CheckCreationError(Exception):
    """Raised when a check cannot be created (validation or quota failure)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _validate_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False


def canonicalize_url(url: str) -> str:
    """Normalize a URL so trivial variants dedup to one entry.

    Lowercases scheme and host, drops default ports (:80, :443), sorts query
    parameters alphabetically, drops the fragment, and collapses an empty
    path to '/'. Preserves path case, trailing slashes on non-root paths,
    and percent-encoding.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parsed.path or "/"

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query_pairs.sort()
    query = urlencode(query_pairs)

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


def clean_url_list(raw_urls: list[str]) -> list[str]:
    """Strip whitespace, validate, canonicalize, deduplicate."""
    seen = set()
    cleaned = []
    for url in raw_urls:
        url = url.strip()
        if not url:
            continue
        if not _validate_url(url):
            continue
        url = canonicalize_url(url)
        if url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned


async def create_and_run_check(urls: list[str], source: str = "manual") -> dict:
    """Validate, quota-check, insert a checks row, and launch run_inspection.

    Shared by the POST /api/checks HTTP handlers and the scheduled auto-run.
    Raises CheckCreationError on validation or quota failures so each caller
    can translate to its preferred error surface.
    """
    if not urls:
        raise CheckCreationError("No URLs provided", status_code=400)

    cleaned = clean_url_list(urls)
    if not cleaned:
        raise CheckCreationError("No valid URLs after validation", status_code=400)

    used = await get_daily_quota_used()
    remaining = DAILY_QUOTA_LIMIT - used
    if len(cleaned) > remaining:
        raise CheckCreationError(
            f"Batch of {len(cleaned)} URLs exceeds remaining daily quota of {remaining}. "
            f"Used {used}/{DAILY_QUOTA_LIMIT} today.",
            status_code=429,
        )

    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO checks (created_at, url_count, property_url, status, source) "
            "VALUES (?, ?, ?, 'running', ?)",
            (now, len(cleaned), GSC_PROPERTY_URL, source),
        )
        check_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()

    asyncio.create_task(run_inspection(check_id, cleaned))

    return {"check_id": check_id, "url_count": len(cleaned), "status": "running"}
