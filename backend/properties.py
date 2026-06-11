import logging
from fnmatch import fnmatch
from typing import Optional
from urllib.parse import urlparse

import aiosqlite

logger = logging.getLogger(__name__)


async def get_all_properties(db: aiosqlite.Connection) -> list[dict]:
    """Fetch all Search Console properties ordered by sort_order (lowest first)."""
    cursor = await db.execute(
        "SELECT id, name, site_url, path_pattern, sort_order "
        "FROM properties ORDER BY sort_order, id"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "site_url": row[2],
            "path_pattern": row[3],
            "sort_order": row[4],
        }
        for row in rows
    ]


def match_url_to_property(url: str, properties: list[dict]) -> Optional[dict]:
    """Return the first property whose path_pattern matches the URL's path.

    Properties are already ordered by sort_order, so the caller controls
    specificity (e.g. `/en-in/*` must have a lower sort_order than `/en/*`).
    """
    path = urlparse(url).path or "/"
    for prop in properties:
        if fnmatch(path, prop["path_pattern"]):
            return prop
    return None


def group_urls_by_property(
    urls: list[str],
    properties: list[dict],
) -> tuple[dict[int, list[str]], list[str]]:
    """Split URLs into {property_id: [urls]} plus a list of unmatched URLs."""
    grouped: dict[int, list[str]] = {}
    unmatched: list[str] = []
    for url in urls:
        prop = match_url_to_property(url, properties)
        if prop:
            grouped.setdefault(prop["id"], []).append(url)
        else:
            unmatched.append(url)
    return grouped, unmatched


def preview_url_properties(urls: list[str], properties: list[dict]) -> list[dict]:
    """For each URL, report which property it would route to (frontend preview)."""
    result = []
    for url in urls:
        prop = match_url_to_property(url, properties)
        result.append({
            "url": url,
            "property_id": prop["id"] if prop else None,
            "property_name": prop["name"] if prop else None,
        })
    return result
